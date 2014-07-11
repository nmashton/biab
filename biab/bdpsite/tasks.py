from __future__ import absolute_import
from celery import shared_task, chain
from utils.bdp import BDP
import utils.osupload as osu
import utils.s3 as s3
from django.utils.text import slugify
import dateutil.parser
from urlparse import urljoin

from bdpsite.models import *

import sys
import traceback
import uuid

from utils.osupload import process_resource, model, os_load
from utils.csv import DatasetCSV
from utils.s3 import put_dataset, put_model
from mimetypes import guess_type

@shared_task
def add(x, y):
    return x + y

@shared_task
def upload_bdp(metadata_url):
    bdp = BDP(metadata_url)
    for resource in bdp.resources:
        # Preprocess the CSV
        osu.process_resource(resource)
        # Create the model for the CSV
        model = osu.model(resource)
        # Post the CSV and model on S3
        name = resource["metadata"]["name"]
        data_url = s3.put_dataset(resource["data"].serialize(), name)
        model_url = s3.put_model(model, name)
        # Call the OS loading API on the result
        osu.os_load(data_url, model_url)

@shared_task
def upload_logo(project_id, logo):
    url = s3.put_content(
        s3.generate_key(uuid.uuid4().hex + logo.name),
        logo.file.read(),
        guess_type(logo.name)
        )
    project = Project.objects.get(id=project_id)
    project.logo_url = url
    project.save()

@shared_task
def create_bdp(project, metadata_url, auto_upload=True):
    # Create an internal representation.
    # This loads the metadata.
    d_obj = BDP(metadata_url)

    # Create a model instance for the new bdp.
    d = DataPackage()
    d.project = project
    d.name = d_obj.metadata["name"]
#    d.slug = slugify(d.name)
    d.path = metadata_url
    d.save()

    # Create model instances for the bdp's resources.
    for resource in d_obj.metadata["resources"]:
        create_dataset.delay(project, d, resource, auto_upload)
    return True

@shared_task
def create_dataset(project, bdp, resource, auto_upload=True):
    d = Dataset()
    d.datapackage = bdp
    d.project = project

    d.path = resource["path"]
    d.name = resource["name"]
    d.currency = resource["currency"]
    d.dateLastUpdated = dateutil.parser.parse(resource["dateLastUpdated"])
    d.datePublished = dateutil.parser.parse(resource["datePublished"])
    d.fiscalYear = dateutil.parser.parse(resource["fiscalYear"])
    d.granularity = resource["granularity"]
    d.status = resource["status"]
    d.type = resource["type"]

    d.description = resource.get("description", "")

    d.save()

    # automatically initiate the process of uploading it to OS
    if auto_upload:
        chain(preprocess_dataset.s({}, d.id) | generate_model.s(d.id) | osload.s(d.id))()

    return True

def reconstruct_resource(dataset, preprocessed=False):
    my_url = dataset.path
    if preprocessed:
        my_url = dataset.preprocessed
    url = urljoin(dataset.datapackage.path, my_url)
    return {
        "data": DatasetCSV(url),
        "metadata": {
            "path": dataset.path,
            "name": dataset.name,

            "currency": dataset.currency,
            "dateLastUpdated": str(dataset.dateLastUpdated),
            "datePublished": str(dataset.datePublished),
            "fiscalYear": str(dataset.fiscalYear)[:4],
            "granularity": dataset.granularity,
            "status": dataset.status,
            "type": dataset.type
        }
    }

@shared_task
def preprocess_dataset(status, id, *args, **kwargs):
    try:
        dataset = Dataset.objects.get(id=id)
        resource = reconstruct_resource(dataset)
        process_resource(resource)
        dataset.preprocessed = put_dataset(dataset.name, resource["data"].serialize())
        dataset.save()
        status.update({"preprocess": "Successfully preprocessed dataset " + dataset.name})
        return status
    except:
        status.update({"preprocess": "Failed to preprocess dataset: " + str(traceback.format_exc())})
        return status

@shared_task
def generate_model(status, id, *args, **kwargs):
    try:
        dataset = Dataset.objects.get(id=id)
        resource = reconstruct_resource(dataset, preprocessed=True)
        dataset_model = model(resource)
        # now do something with dataset_model
        # ... like post it on S3
        # ... and store the result
        dataset.datamodel = put_model(dataset.name, dataset_model)
        dataset.save()
        # dataset.datamodel = s3_url
        status.update({"model": "Successfully generated model for dataset " + dataset.name})
        return status
    except:
        status.update({"model": "Failed to preprocess dataset: " + str(traceback.format_exc())})
        return status

@shared_task
def osload(status, id, *args, **kwargs):
    try:
        dataset = Dataset.objects.get(id=id)
        if dataset.preprocessed is None or dataset.datamodel is None:
            return False
        response_json = os_load(dataset.preprocessed, dataset.datamodel)
        dataset.openspending = response_json["html_url"]
        dataset.save()
        status.update({"openspending": "Successfully uploaded dataset " + dataset.name})
        return status
    except:
        status.update({"openspending": "Failed to send dataset to Openspending: " + str(traceback.format_exc())})
        return status

@shared_task
def process_and_load(dataset):
    """
    Checks to make sure the dataset has associated `preprocessed`
    and `datamodel` attributes. If not, creates them
    (synchronously, because they depend on one another).

    Once everything is in the clear, posts the result on OpenSpending.
    """
    if dataset.preprocessed is None:
        preprocess_dataset.delay(dataset.id).get()
    if dataset.datasetmodel is None:
        generate_model.delay(dataset.id).get()
    return osload.delay(dataset.id)