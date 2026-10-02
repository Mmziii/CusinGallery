"""
Makes User.email nullable and adds a conditional (partial) unique
constraint on it (Phase 3). See the User model's docstring in
apps/accounts/models.py for the full reasoning.

This does NOT touch any existing migration -- accounts/0001-0003 stay
exactly as they were applied. This is a genuinely new migration for a
genuinely new model change, per Phase 3's instruction not to hand-edit
an already-applied migration.

Safety of this specific change: AbstractUser declares
REQUIRED_FIELDS = ["email"], so `createsuperuser` already required a
real (non-blank) email in every earlier phase -- meaning any existing
row's email is guaranteed to be a non-empty string, never blank. Going
from NOT NULL to NULLable is a purely widening, non-destructive schema
change regardless, but that guarantee also means no existing row could
collide with another under the new partial unique constraint.

Hand-authored -- see accounts/migrations/0002_user_phone.py's docstring
for why, and verify with `makemigrations --check --dry-run` before
relying on it in production.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_address"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(
                blank=True,
                help_text=(
                    "Optional for customers. See the class docstring for why this is "
                    "nullable rather than a plain unique CharField."
                ),
                max_length=254,
                null=True,
                verbose_name="email address",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("email__isnull", False)),
                fields=("email",),
                name="user_email_unique_when_set",
            ),
        ),
    ]
