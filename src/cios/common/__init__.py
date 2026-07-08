"""Small, dependency-free utilities shared across cios packages that must
NOT import from each other (brain / dashboard deliberately have no import
dependency on one another -- see their module docstrings). Anything placed
here must stay standalone: no DB, no network, stdlib only.
"""
