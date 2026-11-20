/* Original, isolated CPython 3.12 / Linux metadata scanner. No public provider. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

enum status { OK, UNSAFE, LIMIT, OS_ERROR, CHANGED };
struct scan {
    uint64_t files, bytes, max_files, max_bytes;
    enum status status;
    int error, cleanup_error, python_error;
};

/* Evaluate exactly once without the GIL; save errno before reacquiring it. */
#define IO_CALL(result, saved, expression) do { \
    Py_BEGIN_ALLOW_THREADS \
    errno = 0; \
    (result) = (expression); \
    (saved) = errno; \
    Py_END_ALLOW_THREADS \
} while (0)

static void fail(struct scan *s, enum status status, int error) {
    if (s->status == OK) { s->status = status; s->error = error; }
}

static int signals(struct scan *s) {
    if (!s->python_error && PyErr_CheckSignals() < 0) s->python_error = 1;
    return s->python_error;
}

static void cleanup(struct scan *s, int result, int error) {
    if (result != 0) {
        if (!s->cleanup_error) s->cleanup_error = error;
        fail(s, OS_ERROR, error);
    }
}

static void close_owned(struct scan *s, int fd) {
    int result, saved;
    IO_CALL(result, saved, close(fd));
    /* Linux releases the descriptor even on EINTR. Never retry this number. */
    cleanup(s, result, saved);
}

static int open_directory(struct scan *s, int parent, const char *name) {
    int fd, saved;
    do {
        IO_CALL(fd, saved, openat(parent, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
        if (signals(s)) {
            if (fd >= 0) close_owned(s, fd);
            return -1;
        }
    } while (fd < 0 && saved == EINTR);
    if (fd < 0) fail(s, OS_ERROR, saved);
    return fd;
}

static int stat_entry(struct scan *s, int fd, const char *name, struct stat *info) {
    int result, saved;
    do {
        IO_CALL(result, saved, fstatat(fd, name, info, AT_SYMLINK_NOFOLLOW));
        if (signals(s)) return -1;
    } while (result < 0 && saved == EINTR);
    if (result < 0) fail(s, OS_ERROR, saved);
    return result;
}

static int stat_opened(struct scan *s, int fd, struct stat *info) {
    int result, saved;
    do {
        IO_CALL(result, saved, fstat(fd, info));
        if (signals(s)) return -1;
    } while (result < 0 && saved == EINTR);
    if (result < 0) fail(s, OS_ERROR, saved);
    return result;
}

static int private_directory(const struct stat *info) {
    return S_ISDIR(info->st_mode) && info->st_uid == getuid()
        && (info->st_mode & 07777) == 0700;
}

/* Takes ownership of fd on every path. expected is a stack-owned metadata copy. */
static void walk(struct scan *s, int fd, unsigned depth, const struct stat *expected) {
    if (depth > 10) { fail(s, LIMIT, 0); close_owned(s, fd); return; }
    struct stat opened;
    if (stat_opened(s, fd, &opened) < 0) { close_owned(s, fd); return; }
    if (!private_directory(&opened)) {
        fail(s, UNSAFE, 0); close_owned(s, fd); return;
    }
    if (expected && (expected->st_dev != opened.st_dev || expected->st_ino != opened.st_ino)) {
        fail(s, CHANGED, 0); close_owned(s, fd); return;
    }
    DIR *stream;
    int saved;
    IO_CALL(stream, saved, fdopendir(fd));
    if (stream == NULL) {
        fail(s, OS_ERROR, saved); close_owned(s, fd); (void)signals(s); return;
    }
    if (!signals(s)) {
        int parent = dirfd(stream);
        if (parent < 0) fail(s, OS_ERROR, errno);
        while (s->status == OK && !s->python_error) {
            struct dirent *entry;
            IO_CALL(entry, saved, readdir(stream));
            if (signals(s)) break;
            if (entry == NULL) {
                /* Explicit profile: enumeration errors, including EINTR, refuse. */
                if (saved != 0) fail(s, OS_ERROR, saved);
                break;
            }
            if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
            s->files++;
            if (s->files > s->max_files) { fail(s, LIMIT, 0); break; }
            struct stat info;
            if (stat_entry(s, parent, entry->d_name, &info) < 0) break;
            if (info.st_uid != getuid()) { fail(s, UNSAFE, 0); break; }
            if (S_ISDIR(info.st_mode)) {
                if ((info.st_mode & 07777) != 0700) { fail(s, UNSAFE, 0); break; }
                int child = open_directory(s, parent, entry->d_name);
                if (child < 0) break;
                walk(s, child, depth + 1, &info);
            } else {
                if (!S_ISREG(info.st_mode) || info.st_nlink != 1 || (info.st_mode & 07777) != 0600) {
                    fail(s, UNSAFE, 0); break;
                }
                if (info.st_size < 0 || (uint64_t)info.st_size > s->max_bytes - s->bytes) {
                    fail(s, LIMIT, 0); break;
                }
                s->bytes += (uint64_t)info.st_size;
            }
        }
    }
    int result;
    IO_CALL(result, saved, closedir(stream));
    cleanup(s, result, saved);
    /* An existing Python exception survives every cleanup operation. */
}

static int bounded_integer(PyObject *value, uint64_t maximum, uint64_t *out) {
    if (!PyLong_CheckExact(value)) {
        PyErr_SetString(PyExc_TypeError, "limits must be exact integers"); return -1;
    }
    unsigned long long number = PyLong_AsUnsignedLongLong(value);
    if (PyErr_Occurred()) return -1;
    if (number > maximum) {
        PyErr_SetString(PyExc_ValueError, "limit outside native scan profile"); return -1;
    }
    *out = number;
    return 0;
}

static PyObject *scan_path(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *path, *files, *bytes;
    struct scan s = {0};
    if (!PyArg_UnpackTuple(args, "scan", 3, 3, &path, &files, &bytes)) return NULL;
    if (!PyBytes_CheckExact(path)) {
        PyErr_SetString(PyExc_TypeError, "path must be exact bytes"); return NULL;
    }
    Py_ssize_t length = PyBytes_GET_SIZE(path);
    const char *name = PyBytes_AS_STRING(path);
    if (length < 1 || length > 4095 || memchr(name, '\0', (size_t)length)) {
        PyErr_SetString(PyExc_ValueError, "invalid native scan path"); return NULL;
    }
    if (bounded_integer(files, 262144, &s.max_files) < 0
        || bounded_integer(bytes, 268435456, &s.max_bytes) < 0) return NULL;
    /* Audit veto happens before any directory is opened; no per-entry Python event. */
    if (PySys_Audit("hms.retention.scan.v1", "OOO", path, files, bytes) < 0) return NULL;
    if (signals(&s)) return NULL;
    int fd = open_directory(&s, AT_FDCWD, name);
    if (fd >= 0) walk(&s, fd, 0, NULL);
    if (signals(&s)) return NULL;
    const char *reason = s.status == OK ? "OK" : s.status == UNSAFE
        ? "QUALIFICATION_UNSAFE_FILE" : (s.status == LIMIT || s.status == CHANGED)
        ? "QUALIFICATION_RETENTION_UNKNOWN" : "OS_ERROR";
    return Py_BuildValue("{s:s,s:i,s:i,s:K,s:K,s:O}",
        "reason", reason, "errno", s.error, "cleanupErrno", s.cleanup_error,
        "files", (unsigned long long)s.files, "logicalBytes", (unsigned long long)s.bytes,
        "directoryReplaced", s.status == CHANGED ? Py_True : Py_False);
}

static PyMethodDef methods[] = {
    {"scan", scan_path, METH_VARARGS, "Bounded metadata-only scan; strict private ABI v1."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef definition = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_hms_retention_native_v1",
    .m_doc = "Experimental Linux / CPython 3.12 retention binding.",
    .m_size = 0,
    .m_methods = methods
};
PyMODINIT_FUNC PyInit__hms_retention_native_v1(void) {
    PyObject *module = PyModule_Create(&definition);
    if (module && PyModule_AddIntConstant(module, "ABI_VERSION", 1) < 0) {
        Py_DECREF(module); return NULL;
    }
    return module;
}
