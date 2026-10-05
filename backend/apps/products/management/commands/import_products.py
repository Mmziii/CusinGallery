"""
Bulk product import from CSV/Excel (Phase B - Store management).

Usage:
    python manage.py import_products products.csv
    python manage.py import_products products.xlsx --dry-run
    python manage.py import_products --write-template template.csv

The exact same validation/transaction engine drives the admin's
"import from file" view (apps/products/importing.py), so the CLI and
the admin behave identically.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.products.importing import (
    import_products_from_rows,
    read_rows,
    template_csv,
    update_products_from_rows,
)


class Command(BaseCommand):
    help = (
        "Import products from a CSV or Excel (.xlsx) file. Rows are matched "
        "by SKU: existing SKUs are updated, new ones created. The import is "
        "all-or-nothing: if any row is invalid, nothing is written and every "
        "error is listed with its row number."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            nargs="?",
            help="Path to the .csv or .xlsx file to import.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the file and report what would happen, without saving anything.",
        )
        parser.add_argument(
            "--write-template",
            metavar="PATH",
            help="Write the documented sample/template CSV to PATH and exit.",
        )
        parser.add_argument(
            "--update-only",
            action="store_true",
            help=(
                "Price/stock update mode (Part R4 item 6): minimal columns "
                "sku/price/sale_price/stock; never creates products, never "
                "touches unlisted fields."
            ),
        )

    def handle(self, *args, **options):
        if options["write_template"]:
            path = options["write_template"]
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                handle.write(template_csv())
            self.stdout.write(self.style.SUCCESS(f"Template written to {path}"))
            return

        if not options["file"]:
            raise CommandError("Provide a file to import, or use --write-template.")

        try:
            rows, header = read_rows(options["file"])
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc))

        if options["update_only"]:
            result = update_products_from_rows(rows, header, dry_run=options["dry_run"])
            if not result.ok:
                self.stderr.write(self.style.ERROR("Update rejected -- nothing was saved:"))
                for message in result.errors:
                    self.stderr.write(self.style.ERROR(f"  {message}"))
                raise CommandError(f"{len(result.errors)} validation error(s).")
            if options["dry_run"]:
                self.stdout.write(self.style.SUCCESS(
                    f"Preview: {result.updated} product(s) would change "
                    f"({len(result.changes)} field change(s)), "
                    f"{result.skipped} row(s) unchanged."
                ))
                for change in result.changes[:50]:
                    self.stdout.write(
                        f"  {change['sku']} | {change['label']}: "
                        f"{change['old']} -> {change['new']}"
                    )
                if len(result.changes) > 50:
                    self.stdout.write(f"  ... and {len(result.changes) - 50} more")
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"OK: {result.updated} updated, {result.skipped} unchanged."
                ))
            return

        result = import_products_from_rows(rows, header, dry_run=options["dry_run"])

        if not result.ok:
            self.stderr.write(self.style.ERROR("Import rejected -- nothing was saved:"))
            for message in result.errors:
                self.stderr.write(self.style.ERROR(f"  {message}"))
            raise CommandError(f"{len(result.errors)} validation error(s).")

        verb = "would be imported" if options["dry_run"] else "imported"
        self.stdout.write(self.style.SUCCESS(
            f"OK: {result.created} created, {result.updated} updated "
            f"({result.created + result.updated} rows {verb})."
        ))
