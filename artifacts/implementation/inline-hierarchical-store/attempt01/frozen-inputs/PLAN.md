# Isolated inline-metadata candidate

Use the prior statx block provider unchanged, including full fsync of every
backing chunk at each block sync. Change only the native bridge's explicit
inline_max from disabled to 512 bytes and the hierarchy's explicit storage
profile. Keep the exact upstream littlefs core, 4096-byte block/read/cache,
16-byte program size, 16 KiB native file limit, finite namespace/handle bounds,
publication/recovery methods and 128 MiB complete-workload geometry.

The new profile is hms.hierarchical-chunk-store.inline512/0.1. Old anchors and
old on-disk profile values refuse; no silent migration or reopening failed old
images. The physical littlefs representation and native callback counts may
change. All logical operations, namespace, full payload bodies and inode metadata
must remain equivalent except for the declared superblock profile.

Before execution: revalidate source seals, record selected inline/outline and
directory-commit review, fully read test_files.toml, freeze all inputs and review
the two production changes. Build only the original bridge/core/utility plus an
original native probe. Do not run upstream scripts, Makefiles or test harnesses.

Run native boundary vectors at 0, 1, 511, 512, 513, 4096 and 16384 bytes and return
transitions to 512/0, plus 300 small files, rename/remove and cold readback. The
probe inspects actual native inline flags and retains modeled RAM snapshots;
its sync callback model does not establish physical durability. Run profile
refusals, the original 24 provider/52 mount controls and all 96 hierarchy controls.
Then run one paired 40-file/20-directory screen with 426 logical steps and complete
warm/cold readback. Compare logical results; record changed callbacks/allocation
without requiring identical raw encodings.

If prior scopes pass, run the complete original 4,270-file/35,508,922-byte writer
and dependent cold reader, with all 169 directories and eight 16 MiB chunks.
Ordinary children: 60 wall/40 CPU seconds, 512 MiB address space, 128 descriptors,
16 MiB per file. Builds: 30 wall/20 CPU. Full writer/reader: 180 wall/120 CPU each.
Retained stage below 1 GiB. Stop on first failure, retain all artifacts, no
unchanged retry, repair, geometry expansion or reduced workload.

Audit retained filesystem state read-only with the new profile explicitly
recognized; forbidden write/erase/sync callbacks and no adapter recovery or SQLite.
Preserve prior images/seals and all 244 public inputs. No public install, actual
mount change, device port, flashing, physical power cut or administrator action.
