import boto3
from datetime import datetime


def create_snapshot(ec2, reg):
    result = ec2.describe_volumes(
        Filters=[
                {
                    'Name': 'status',
                    'Values': ['in-use']
                },
                {
                    'Name': 'tag:Backup',
                    'Values': ['yes']
                }
            ]
        )

    for volume in result['Volumes']:
        print "Backing up %s in %s" % (volume['VolumeId'], volume['AvailabilityZone'])
        # Create snapshot
        result = ec2.create_snapshot(
            VolumeId=volume['VolumeId'],
            Description='Created by Lambda backup function {{ lambda_function_name }}'
            )
        # Get snapshot resource
        ec2resource = boto3.resource('ec2', region_name=reg)
        snapshot = ec2resource.Snapshot(result['SnapshotId'])

        snapshot_tags = []
        # Find name tag for volume if it exists
        if 'Tags' in volume:
            for tags in volume['Tags']:
                if tags["Key"] in ['Name', 'Backup']:
                    snapshot_tags.append({'Key': tags["Key"],'Value': tags["Value"]})
        # Add volume name to snapshot for easier identification
        snapshot.create_tags(Tags=snapshot_tags)

def cleanup_old_snapshots(
        ec2resource,
        retention_days=7,
        filters=[
                {
                    'Name': 'tag:Name',
                    'Values': ['*']
                },
                {
                    'Name': 'tag:Backup',
                    'Values': ['yes']
                }
            ],
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
            print 'Deleting {id}'.format(id=snapshot.snapshot_id)
            deletion_counter = deletion_counter + 1
            size_counter = size_counter + snapshot.volume_size
            # Just to make sure you're reading!
            snapshot.delete(DryRun=dry_run)

    print 'Deleted {number} snapshots totalling {size} GB'.format(
        number=deletion_counter,
        size=size_counter
        )


def lambda_handler(event, context):
    regions = {{ regions|default([region]) }}
    # Iterate over regions
    for reg in regions:
        ses = boto3.session.Session()

        ec2 = ses.client('ec2', region_name=reg)
        create_snapshot(ec2, reg)

        ec2resource = ses.resource('ec2', region_name=reg)
        cleanup_old_snapshots(ec2resource, retention_days={{ retention_days|default(7) }})

    return 'OK'
