from django.db import models

class Parking(models.Model):
    location = models.CharField(max_length=100)
    