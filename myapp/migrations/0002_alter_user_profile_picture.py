# Generated by Django 5.1.2 on 2024-10-19 08:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='profile_picture',
            field=models.ImageField(upload_to='profile_picture'),
        ),
    ]
