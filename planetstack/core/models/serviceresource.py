import os
from django.db import models
from core.models import PlCoreBase
from core.models import Site
from core.models import Deployment
from core.models import ServiceClass

# Create your models here.

class ServiceResource(PlCoreBase):
    serviceClass = models.ForeignKey(ServiceClass, related_name = "resources")
    name = models.CharField(max_length=32)
    maxUnitsDeployment = models.IntegerField(default=1)
    maxUnitsNode = models.IntegerField(default=1)
    maxDuration = models.IntegerField(default=1)
    bucketInRate = models.IntegerField(default=0)
    bucketMaxSize = models.IntegerField(default=0)
    cost = models.IntegerField(default=0)
    calendarReservable = models.BooleanField(default=True)

    def __unicode__(self):  return u'%s' % (self.name)
