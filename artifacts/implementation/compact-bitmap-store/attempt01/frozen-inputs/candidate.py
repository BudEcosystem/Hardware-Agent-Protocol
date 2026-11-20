"""Compact-bitmap hierarchy with the pinned statx block-provider identity."""
from hierarchical_store import HierarchicalStore as Original


class HierarchicalStore(Original):
    BLOCK_HASH = '7bace462fdeb6257ab6ed3d8d65da2040ac87456c1984a13840177a9516e187b'
