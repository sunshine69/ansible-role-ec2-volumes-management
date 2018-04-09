ansible-role-ec2-volumes-management
=========

Implement snapshot backup and cleanup.

This role will:

- Scan all volumes in the `regions` with tag Backup: yes and Status: in-use (you can custom the Filter - see example)

  Then create a snapshot backup daily. Snapshot will be tag with the same 'Name' and a key 'Backup'

- Scan all snapshot in the `regions` with creation time longer than `retention_days` days with tag 'Name': '\*' and 'Backup': yes - again it can be customised with your own filters.

  Then remove them except the last 1 backup

- Scan and remove all snapshots that was created by the AMI launch but AMI has already been de-registered.

- Scan all AMI and then deregister ami if:

  - No (running/stopped) ec2 instances use it
  - Matching the filters condition
  - creation time older than `retention_days`

Requirements
------------

- `ansible-role-aws-lambda` - Required. See https://github.com/willthames/ansible-role-aws-lambda

  This is to create the lambda function and the cloudwatch event to do run the
  python scripts which do the actual mainteance


Role Variables
--------------

- `aws_account_id` - Required - The account id that you want to scan for objects.


- `iam_role_name` - Optional - Default:  'volume-management-iam-role'

  The IAM role to run the lambda function as. The IAM role will be created by
  this role to have enough permissions.

- `lambda_function_name` - Optional - Default: "ec2_vol_management"

  If you want to deploy multiple lambda for different type of volumes you can
  call this role and override the `lambda_function_name` and per each call set
  the `lambda_environment` (see below) differently.

- `lambda_runtime` - Optional - Default: python2.7


- `lambda_scheduled_rule_expression` - Optional - Default:  'cron(0 12 * * ? *)'

  Default run daily. Note that this is GMT time in aws event


- `lambda_environment` - Optional - A dict to set the env variable for the python script

  The keys are followed
  - `REGIONS` - coma separated region string - default "`region`,". We will scan object for each region
  - `RETENTION_DAYS` - number of days to keep

  - `SNAPSHOT_CREATE_FILTER`
  - `SNAPSHOT_DELETE_FILTER`
  - `AMI_DEREGISTER_FILTER`

  Optional - default value in the example below.

  They are a python string which will be evaluated into a python list of
  filters. See example below.

  Examples:

  ```
  lambda_environment:
    REGIONS: "ap-southeast-2,"
    RETENTION_DAYS: "14"
    SNAPSHOT_CREATE_FILTER: '[{"Name":"tag:Backup", "Values": ["yes"]}, {"Name": "status", "Values": ["in-use"]}]'
    SNAPSHOT_DELETE_FILTER: '[{"Name":"tag:Backup", "Values": ["yes"]}, {"Name": "tag:Name", "Values": ["*"]}]'
    AMI_DEREGISTER_FILTER: '[{"Name": "tag:Application", "Values": ["*"]}]'
  ```

- `lambda_scheduled_rule_expression` - Optional - Default: 'cron(0 1 \* \* ? \*)' (run daily)


Dependencies
------------


Example Playbook
----------------

```
- hosts: localhost
  vars:
    lambda_environment:
      REGIONS: "ap-southeast-2,"
      RETENTION_DAYS: 14

    profile: "act2_non_prod"
  roles:
    - ec2-volumes-management
```

License
-------

BSD

Author Information
------------------

Steve Kieu, XVT Solutions (steve.kieu@xvt.com.au)
