import ast
import boto3, botocore
from datetime import datetime, timedelta
import logging
import os
import re

#setup logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def create_snapshot(ec2, reg, filters=[], context={}):
    result = ec2.describe_volumes(Filters=filters)

    for volume in result['Volumes']:
        logger.info("Backing up %s in %s" % (volume['VolumeId'], volume['AvailabilityZone']))
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
                logger.info("Deleting %s" % snapshot.snapshot_id)
                if not dry_run:
                    snapshot.delete(DryRun=dry_run)
                else:
                    logger.info("    skipped as dry_run is true")


def cleanup_old_snapshots(
        ec2resource,
        retention_days=7,
        filters=[],
        keep_at_least=1,
        dry_run=True):

    delete_time = int(datetime.now().strftime('%s')) - retention_days * 86400

    logger.info('Deleting any snapshots older than {days} days'.format(days=retention_days))

    snapshot_iterator = ec2resource.snapshots.filter(Filters=filters)
    get_last_start_time = lambda obj: int(obj.start_time.strftime('%s'))
    snapshots = sorted([ x for x in snapshot_iterator ], key=get_last_start_time)

    deletion_counter = 0
    size_counter = 0
    total_snapshots = len(snapshots)

    snapshots_to_delete = snapshots[0:-1 * keep_at_least]

    for snapshot in snapshots_to_delete:
        start_time = int(snapshot.start_time.strftime('%s'))

        if start_time < delete_time:
            deletion_counter = deletion_counter + 1
            size_counter = size_counter + snapshot.volume_size
            logger.info('Deleting {id}'.format(id=snapshot.snapshot_id))
            if not dry_run:
                snapshot.delete()
            else:
                logger.info("   skipped as dry_run is true")
    logger.info('Deleted {number} snapshots totalling {size} GB'.format(
        number=deletion_counter,
        size=size_counter
        ))


def deregister_ami(ec2, aws_account_id, filters=[], retention_days=14, dry_run=True):
    """Deregister ami if:
    - No (running/stopped) ec2 instances use it
    - Matching the filters condition
    - creation time older than retention_days
    - Retain at least one ami for safety

    """
    instances = ec2.instances.all()
    images = ec2.images.filter(Owners=[aws_account_id], Filters=filters)
    images_in_use = set([instance.image_id for instance in instances])
    images_to_deregister_dict = { image.id: image for image in images if image.id not in images_in_use }

    images_to_deregister_list = images_to_deregister_dict.values()
    images_to_deregister_list = sorted(images_to_deregister_list, key=lambda x: x.creation_date)
    # Keep the last one
    images_to_deregister_list = images_to_deregister_list[0:-1]
    if len(images_to_deregister_list) == 0:
        return {}

    all_snapshots = ec2.snapshots.filter(OwnerIds=[aws_account_id])
    # deregister all the AMIs older than retention_days
    today = datetime.now()
    date_to_keep = today - timedelta(days=retention_days)
    for image in images_to_deregister_list:
        created_date = datetime.strptime(image.creation_date, "%Y-%m-%dT%H:%M:%S.000Z")
        logger.info(created_date)
        logger.info(image.creation_date)
        if created_date < date_to_keep:
            logger.info("Deregistering %s" % image.id)
            if not dry_run:
                image.deregister()
                for snapshot in all_snapshots:
                    #get the ami id (that the snapshot belongs to) from the snapshot's description
                    r = re.match(r".*for (ami-.*) from.*", snapshot.description)
                    if r:
                        #r.groups()[0] will contain the ami id
                        if r.groups()[0] == image.id:
                            logger.info("found snapshot belonging to %s. snapshot with image_id %s will be deleted", image.id, snapshot.snapshot_id)
                            snapshot.delete()
            else:
                logger.info("    skipped as dry_run is true")


# Takes a list of EC2 instances with tag 'ami-creation': true - IDs and creates AMIs
# Copy from one of my work mate into here with small modification
def create_amis(ec2, cycle_tag='daily'):
    ec2_filter = [{'Name':'tag:ami-creation', 'Values':['true']}]
    instances = list(ec2.instances.filter(Filters=ec2_filter))

    logger.info("create AMIs with cycle_tag: '%s'", cycle_tag)

    #creat image for each instance
    for instance in instances:
        for tag in instance.tags:
            if tag['Key'] == 'Name':
                instance_name = tag['Value']
        logger.info("creating image for ' %s' with name: %s",instance.id, instance_name)

        try:
            utc_now = datetime.utcnow()
            name = '%s-%s %s/%s/%s %s-%s-%sUTC' % (cycle_tag,
                                                   instance_name,
                                                   utc_now.day,
                                                   utc_now.month,
                                                   utc_now.year,
                                                   utc_now.hour,
                                                   utc_now.minute,
                                                   utc_now.second)
            #AMIs names cannot contain ','
            name = name.replace(',', '_').replace(':', '_')

            image = instance.create_image(
                DryRun=False,
                Name=name,
                Description='AMI of ' + instance.id + ' created with Lambda function',
                NoReboot=True
            )

            logger.info('call to create_image succeeded')

            #create tag(s)
            image.create_tags( Tags=[
                {'Key': 'ami-cycle', 'Value': cycle_tag},
                {'Key': 'Name', 'Value': name}
                ])

        except botocore.exceptions.ClientError as err:
            logger.info('caught exception: Error message: %s', err)



def lambda_handler(event, context):
    regions = os.environ.get('REGIONS', 'ap-southeast-2').split(',')
    ses = boto3.session.Session()
    aws_account_id = os.environ.get('AWS_ACCOUNT_ID')
    retention_days = int(os.environ.get('RETENTION_DAYS', 14))

    # If volume is 'in-use' and having tag:Backup = 'yes' then we create snapshot
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

    # Delete these snapshot created by this script only
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

    ami_deregister_filters_default = [
            [
		        {
		            'Name': 'tag:ami-cycle',
		            'Values': ['*']
        	    },
                {
                    'Name': 'tag:Application',
                    'Values': ['ecs-agent']
                },
                {
                    'Name': 'tag:Environment',
                    'Values': ['int']
                }
            ],
            [
                {
                    'Name': 'tag:Application',
                    'Values': ['ecs-agent']
                },
                {
                    'Name': 'tag:Environment',
                    'Values': ['qa']
                }
            ],
            [
                {
                    'Name': 'tag:BuildLayer',
                    'Values': ['system']
                },
                {
                    'Name': 'tag:Version',
                    'Values': ['ubuntu-1604']
                }
            ],
            [
                {
                    'Name': 'tag:BuildLayer',
                    'Values': ['system']
                },
                {
                    'Name': 'tag:Version',
                    'Values': ['ubuntu-1804']
                }
            ],
            [
                {
                    'Name': 'tag:BuildLayer',
                    'Values': ['platform']
                },
                {
                    'Name': 'tag:Platform',
                    'Values': ['java']
                }
            ]
        ]

    ami_deregister_filters = ast.literal_eval( os.environ.get('AMI_DEREGISTER_FILTER', "None"))
    ami_deregister_filters = ami_deregister_filters if ami_deregister_filters else ami_deregister_filters_default

    # Iterate over regions

    cycle_tag = event.get('cycle_tag', 'daily')
    for reg in regions:
        if not reg: continue
        ec2 = ses.client('ec2', region_name=reg)

        create_snapshot(ec2, reg, filters=snapshot_create_filter, context=context)

        ec2resource = ses.resource('ec2', region_name=reg)

        cleanup_old_snapshots(ec2resource, retention_days=retention_days, filters=snapshot_delete_filter, dry_run=False)

        cleanup_detach_snapshot(ec2resource, aws_account_id, dry_run=False)

        create_amis(ec2resource, cycle_tag)

        for ami_deregister_filter in ami_deregister_filters:
            deregister_ami(ec2resource, aws_account_id, filters=ami_deregister_filter, dry_run=False)

    return 'OK'
