/* Test-only translation unit. These controls never occur in the production DSO. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
int fault_openat(int, const char *, int, ...);
int fault_fstatat(int, const char *, struct stat *, int);
int fault_fstat(int, struct stat *);
DIR *fault_fdopendir(int);
struct dirent *fault_readdir(DIR *);
int fault_close(int);
int fault_closedir(DIR *);
#define openat fault_openat
#define fstatat fault_fstatat
#define fstat fault_fstat
#define fdopendir fault_fdopendir
#define readdir fault_readdir
#define close fault_close
#define closedir fault_closedir
#define PyInit__hms_retention_native_v1 base_module_init
#include "scanmodule.c"
#undef openat
#undef fstatat
#undef fstat
#undef fdopendir
#undef readdir
#undef close
#undef closedir
#undef PyInit__hms_retention_native_v1
#include <stdarg.h>

enum operation { F_OPEN, F_STAT_ENTRY, F_STAT_OPEN, F_STREAM, F_READ, F_CLOSE, F_CLOSE_STREAM, F_COUNT };
static unsigned calls[F_COUNT];
static int selected = -1, selected_errno, action;
static unsigned occurrence;
static int trigger(enum operation op) {
    calls[op]++;
    return selected == (int)op && calls[op] == occurrence;
}

int fault_openat(int parent, const char *name, int flags, ...) {
    if (trigger(F_OPEN)) {
        if (action == 1) {
            /* Own fixture only: substitute a distinct real 0700 directory. */
            if (renameat(parent, name, parent, "retired") != 0
                || renameat(parent, "../spare", parent, name) != 0) return -1;
        } else { errno = selected_errno; return -1; }
    }
    return openat(parent, name, flags);
}
int fault_fstatat(int parent, const char *name, struct stat *info, int flags) {
    if (trigger(F_STAT_ENTRY)) {
        if (action == 2) {
            if (unlinkat(parent, name, 0) != 0) return -1;
        } else { errno = selected_errno; return -1; }
    }
    return fstatat(parent, name, info, flags);
}
int fault_fstat(int fd, struct stat *info) {
    if (trigger(F_STAT_OPEN)) { errno = selected_errno; return -1; }
    return fstat(fd, info);
}
DIR *fault_fdopendir(int fd) {
    if (trigger(F_STREAM)) { errno = selected_errno; return NULL; }
    return fdopendir(fd);
}
struct dirent *fault_readdir(DIR *stream) {
    if (trigger(F_READ)) { errno = selected_errno; return NULL; }
    return readdir(stream);
}
int fault_close(int fd) {
    int inject = trigger(F_CLOSE);
    int result = close(fd);
    if (action == 3) { errno = EINTR; return -1; }
    if (inject) { errno = selected_errno; return -1; }
    return result;
}
int fault_closedir(DIR *stream) {
    int inject = trigger(F_CLOSE_STREAM);
    int result = closedir(stream);
    if (inject) { errno = selected_errno; return -1; }
    return result;
}

static PyObject *configure(PyObject *self, PyObject *args) {
    (void)self;
    int op, error, behavior;
    unsigned nth;
    if (!PyArg_ParseTuple(args, "iIii", &op, &nth, &error, &behavior)) return NULL;
    if (op < -1 || op >= F_COUNT || nth > 1000 || behavior < 0 || behavior > 3) {
        PyErr_SetString(PyExc_ValueError, "test configuration out of range"); return NULL;
    }
    memset(calls, 0, sizeof(calls));
    selected = op; occurrence = nth; selected_errno = error; action = behavior;
    Py_RETURN_NONE;
}
static PyObject *counters(PyObject *self, PyObject *ignored) {
    (void)self; (void)ignored;
    return Py_BuildValue("[IIIIIII]", calls[0], calls[1], calls[2], calls[3], calls[4], calls[5], calls[6]);
}
static PyMethodDef test_methods[] = {
    {"configure", configure, METH_VARARGS, "Test-only deterministic call injection."},
    {"counters", counters, METH_NOARGS, "Test-only call counts."},
    {NULL, NULL, 0, NULL}
};
PyMODINIT_FUNC PyInit__hms_retention_native_v1(void) {
    PyObject *module = base_module_init();
    if (module && PyModule_AddFunctions(module, test_methods) < 0) {
        Py_DECREF(module); return NULL;
    }
    return module;
}
