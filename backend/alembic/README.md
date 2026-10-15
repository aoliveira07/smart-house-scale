# Migration integration note

Copy `versions/20261015_0001_scale_v1.py` into the existing Smart House Alembic
versions directory and set `down_revision` to the current migration head before
running the normal migration command. The module does not create a second
Alembic environment or a second database.
