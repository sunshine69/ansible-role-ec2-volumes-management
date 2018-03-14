ansible-role-ec2-volumes-management
=========

Implement snapshot backup and cleanup.

This role will:
- Scan all volumes in the `regions` with tag Backup: yes and Status: in-use
- Then create a snapshot backup daily. Snapshot will be tag with the same 'Name' and a key 'Backup'

- Scan all snapshot the `regions` with creation time longer than `retention_days` days with tag 'Name': '\*' and 'Backup': yes
- Then remove them


Requirements
------------

- `aws_profile_account` - Optional

  If you run without supplying the variable `profile` and `region` it will use a role
  `aws_profile_account` which will try to assume a IAM role
  `profile_account_role_arn` to obtain the permission to do the task.

- `ansible-role-aws-lambda` - Required. See https://github.com/willthames/ansible-role-aws-lambda

  This is to create the lambda function and the cloudwatch event to do run the
  python scripts which do the actual mainteance


Role Variables
--------------

- `regions` - Optional - A string with python syntax as a python list of all
  region you want to scan for volumes and snapshots.

  Default value is a list with one element taking the current variable `region`

- `retention_days` - Optional - Default: 7 - Number of days to keep snapshot.

- `iam_role_name` - Options - Default:  "volume-management-iam-role"

  The iam role name to be used for lambda

- `lambda_function_name` - Optional - Default:  "ec2-vol-management"

- `lambda_runtime` - Optional - Default: python2.7

- `lambda_scheduled_rule_expression` - Optional - Default: 'cron(0 1 * * ? *)' (run daily)


Dependencies
------------


Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

    - hosts: servers
      roles:
         - { role: username.rolename, x: 42 }

License
-------

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
