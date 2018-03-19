import ast
import boto3
from datetime import datetime, timedelta

import os
import re

def create_snapshot(ec2, reg, filters=[], context={}):
    result = ec2.describe_volumes(Filters=filters)

    for volume in result['Volumes']:
        print "Backing up %s in %s" % (volume['VolumeId'], volume['AvailabilityZone'])
        # Create snapshot
        result = ec2.create_snapshot(
            VolumeId=volume['VolumeId'],
            Description='Created by Lambda function %s for backup from %s' % (context.function_name, volume['VolumeId'])
          )
        # Get snapshot resource
        ec2resource = boto3.resource('ec2', region_name=reg)
        snapshot = ec2resource.Snapshot(result['SnapshotId'])

        snapshot_tags = []
        # Find name tag for volume if it exists
        if 'Tags' in volume:
            for tags in volume['Tags']:
                snapshot_tags.append({'Key': tags["Key"],'Value': tags["Value"]})
        # Add volume name to snapshot for easier identification
        snapshot.create_tags(Tags=snapshot_tags)

def cleanup_detach_snapshot(ec2, aws_account_id, dry_run=True):
    """This will delete all snapshot that is created automatically by the aws related to ami image but the ami is no longer available (by de-registering)
    """
    images = ec2.images.filter(Owners=[aws_account_id])
    images = [image.id for image in images]
    for snapshot in ec2.snapshots.filter(OwnerIds=[aws_account_id]):
        r = re.match(r".*for (ami-.*) from.*", snapshot.description)
        if r:
            if r.groups()[0] not in images:
                print("Deleting %s" % snapshot.snapshot_id)
                if not dry_run:
                    snapshot.delete(DryRun=dry_run)
                else:
                    print("    skipped as dry_run is true")

def deregister_ami(ec2, aws_account_id, filters=[], retention_days=14, dry_run=True):
    """Deregister ami if:
    - No (running/stopped) ec2 instances use it
    - Matching the filters condition
    - creation time older than retention_days

    """
    instances = ec2.instances.all()
    images = ec2.images.filter(Owners=[aws_account_id], Filters=filters)
    images_in_use = set([instance.image_id for instance in instances])
    images_to_deregister_dict = { image.id: image for image in images if image.id not in images_in_use }
    # deregister all the AMIs older than retention_days
    today = datetime.now()
    date_to_keep = today - timedelta(days=retention_days)
    for image in images_to_deregister_dict.values():
        created_date = datetime.strptime(image.creation_date, "%Y-%m-%dT%H:%M:%S.000Z")
        print(created_date)
        print(image.creation_date)
        if created_date < date_to_keep:
            print("Deregistering %s" % image.id)
            if not dry_run:
                image.deregister()
            else:
                print("    skipped as dry_run is true")

def cleanup_old_snapshots(
        ec2resource,
        retention_days=7,
        filters=[],
        keep_at_least=1,
        dry_run=True):

    delete_time = int(datetime.now().strftime('%s')) - retention_days * 86400

    print 'Deleting any snapshots older than {days} days'.format(days=retention_days)

    snapshot_iterator = ec2resource.snapshots.filter(Filters=filters)
    get_last_start_time = lambda obj: int(obj.start_time.strftime('%s'))
    snapshots = sorted([ x for x in snapshot_iterator ], key=get_last_start_time)

    deletion_counter = 0
    size_counter = 0
    total_snapshots = len(snapshots)

    snapshots_to_delete = snapshots[0:keep_at_least]

    for snapshot in snapshots_to_delete:
        start_time = snapshot.start_time.strftime('%s')

        if start_time < delete_time:
            deletion_counter = deletion_counter + 1
            size_counter = size_counter + snapshot.volume_size
            print 'Deleting {id}'.format(id=snapshot.snapshot_id)
            if not dry_run:
                snapshot.delete()
            else:
                print("   skipped as dry_run is true")
    print 'Deleted {number} snapshots totalling {size} GB'.format(
        number=deletion_counter,
        size=size_counter
        )


def lambda_handler(event, context):

    regions = os.environ.get('REGIONS', 'ap-southeast-2').split(',')
    ses = boto3.session.Session()
    aws_account_id = os.environ.get('AWS_ACCOUNT_ID')
    retention_days = int(os.environ.get('RETENTION_DAYS', 14))

    snapshot_create_filter_default = [
                {
                    'Name': 'status',
                    'Values': ['in-use']
                },
                {
                    'Name': 'tag:Backup',
                    'Values': ['yes']
                }
            ]
    snapshot_create_filter = ast.literal_eval( os.environ.get('SNAPSHOT_CREATE_FILTER', "None"))
    snapshot_create_filter = snapshot_create_filter if snapshot_create_filter else snapshot_create_filter_default

    snapshot_delete_filter_default = [
                {
                    'Name': 'tag:Name',
                    'Values': ['*']
                },
                {
                    'Name': 'tag:Backup',
                    'Values': ['yes']
                }
            ]
    snapshot_delete_filter = ast.literal_eval( os.environ.get('SNAPSHOT_DELETE_FILTER', "None"))
    snapshot_delete_filter = snapshot_delete_filter if snapshot_delete_filter else snapshot_delete_filter_default


    ami_deregister_filter_default = [
        {
            'Name': 'tag:Application',
            'Values': ['*']
        }
    ]
    ami_deregister_filter = ast.literal_eval( os.environ.get('AMI_DEREGISTER_FILTER', "None"))
    ami_deregister_filter = ami_deregister_filter if ami_deregister_filter else ami_deregister_filter_default

    # Iterate over regions

    for reg in regions:
        if not reg: continue
        ec2 = ses.client('ec2', region_name=reg)
        create_snapshot(ec2, reg, filters=snapshot_create_filter, context=context)

        ec2resource = ses.resource('ec2', region_name=reg)

        cleanup_old_snapshots(ec2resource, retention_days=retention_days, filters=snapshot_delete_filter, dry_run=False)
        cleanup_detach_snapshot(ec2resource, aws_account_id, dry_run=False)
        deregister_ami(ec2resource, aws_account_id, filters=ami_deregister_filter, dry_run=False)

    return 'OK'
