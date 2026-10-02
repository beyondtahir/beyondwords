"""Atomic, exclusive local artifact writes shared by inherited helpers."""
import os
from pathlib import Path
import tempfile


def write_new(path,data):
    target=Path(path)
    if not isinstance(data,bytes):raise TypeError('bytes required')
    fd,temporary=tempfile.mkstemp(prefix='.bw-artifact-',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        # Linking is atomic and refuses an existing target, including symlinks.
        os.link(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
