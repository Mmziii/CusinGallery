import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0012_compact_featured_label'),
        ('wishlist', '0003_alter_wishlistitem_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wishlistitem',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='تاریخ افزودن'),
        ),
        migrations.AlterField(
            model_name='wishlistitem',
            name='product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wishlisted_by', to='products.product', verbose_name='محصول'),
        ),
    ]
