"""Record-provenance helpers shared by the sim/ summarizers.

Stdlib only. Importers put sim/lib on sys.path (the summarizers run with -I,
which does not add the script directory or the current one):

    sys.path.insert(0, os.path.join(HERE, "..", "lib"))
    from provenance import sha, commit_line
"""
import hashlib


def sha(path):
    """sha256 hex digest of the file at `path`."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def commit_line(git_sha, dirty):
    """The record's `- Commit:` provenance bullet; `dirty` is the "0"/"1" CLI arg."""
    return f"- Commit: `{git_sha}`" + (" (**working tree dirty** when run)" if dirty == "1" else "")
