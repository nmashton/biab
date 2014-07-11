from django.db import models
from django.contrib.auth.models import User
from autoslug import AutoSlugField
import re
import datetime

# Create your models here.

class Project(models.Model):
    title = models.CharField(max_length=256)
    slug = AutoSlugField(populate_from="title", 
        unique=True, 
        editable=True)
    description = models.TextField(default="")
    creator = models.ForeignKey(User)

    featured_viz = models.ForeignKey("Visualization",null=True,blank=True)
    logo_url = models.URLField(null=True,blank=True)

    def __unicode__(self):
        return self.title

class DataPackage(models.Model):
    name = models.CharField(max_length=256)
    project = models.ForeignKey(Project)
    slug = AutoSlugField(populate_from="name", 
        unique_with="project__slug", 
        editable=True)
    path = models.URLField(null=True)

    def __unicode__(self):
        return self.name

class Dataset(models.Model):
    # the BDP that contains the dataset
    datapackage = models.ForeignKey(DataPackage,null=True,blank=True)
    project = models.ForeignKey(Project)

    # the creation date of the dataset
    created = models.DateTimeField(auto_now_add=True, default=datetime.datetime.today())

    # URLs linking to OS stuff
    preprocessed = models.URLField(null=True,blank=True)
    datamodel = models.URLField(null=True,blank=True)
    openspending = models.URLField(null=True,blank=True)

    # stuff from BDP resource metadata
    path = models.CharField(max_length=256,null=True,blank=True)
    name = models.CharField(max_length=256)
    currency = models.CharField(max_length=256)
    dateLastUpdated = models.DateTimeField(blank=True)
    datePublished = models.DateTimeField(blank=True)
    fiscalYear = models.DateTimeField(null=True,blank=True)
    granularity = models.CharField(max_length=256,null=True, blank=True)
    status = models.CharField(max_length=256,null=True, blank=True)
    type = models.CharField(max_length=256)
    description = models.TextField(null=True,blank=True)
    
    @property
    def openspendingSlug(self):
        return re.match("http[s]*://[a-zA-Z0-9-.]+/([a-z0-9-]+)/?",
                        self.openspending).group(1)

    def __unicode__(self):
        return self.name

class Visualization(models.Model):
    dataset = models.ForeignKey(Dataset)
    order = models.IntegerField(default=0)
    drilldowns = models.CharField(max_length=512)
    cuts = models.CharField(max_length=512,null=True,blank=True)
    type = models.CharField(max_length=20,
        choices = (
            ("bubbletree","Bubble Tree"),
            ("barchart", "Bar Chart"),
            ("treemap", "Tree Map"),
            ("linebars" ,"Line Bars"),
            ("stackedbar", "Stacked Bar Charts"),
            ))
    description = models.TextField(blank=True,null=True)

    def __unicode__(self):
        return u"%s of %s"%(self.type,self.dataset.name)
