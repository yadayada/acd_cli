acd_cli
=======

**acd_cli** aims to provide a command line interface to Amazon Cloud Drive written in Python 3. It is currently in alpha stage.

##Features

 * local node caching
 * addressing of nodes via a pathname (e.g. `/Photos/kitten.jpg`)
 * tree listing of files and folders
 * upload/download of single files and directories
 * background hashing
 * folder creation
 * trashing/restoring
 * moving/renaming nodes

##Planned
 
 * "smart" folder syncing
 * shell completion for remote paths
 * ... minor stuff

##Quick start

On the first start of the program (try ``./acd_cli.py sync``), you will have to complete the OAuth procedure.
A browser tab will open and you will be asked to log in or grant access for 'acd_cli_oa'.
Signing in or clicking on 'Continue' will download a JSON file named `oauth_data`,
which must be placed in the application directory.

You may view the Appspot source code at https://tensile-runway-92512.appspot.com/src. 

##Usage

The following actions are built in

```
    sync (s)            refresh node list cache; necessary for many actions
    clear-cache (cc)    clear node cache [offline operation]
    tree (t)            print directory tree [offline operation]
    upload (ul)         file and directory upload to a remote destination
    overwrite (ov)      overwrite file A [remote] with content of file B [local]
    download (dl)       download a remote folder or file; will overwrite local files
    open (o)            open node
    create (c, mkdir)   create folder using an absolute path
    list-trash (lt)     list trashed nodes [offline operation]
    trash (rm)          move node to trash
    restore (re)        restore from trash
    children (ls)       list folder's children [offline operation]
    move (mv)           move node A into folder B
    rename (rn)         rename a node
    resolve (rs)        resolve a path to a node ID
    find (f)            find nodes by name [offline operation]
    add-child (ac)      add a node to a parent folder
    remove-child (rc)   remove a node from a parent folder
    usage (u)           show drive usage data
    quota (q)           show drive quota (raw JSON)
    metadata (m)        print a node's metadata (raw JSON)
```

Please run ``./acd_cli.py --help`` to get a current list of the available actions. You may also get a list of  further arguments and their order of an action by calling ``./acd_cli.py [action] --help``.

You may provide most node arguments as a 22 character ID or a UNIX-style path. Trashed nodes' paths might not be able to be resolved correctly; use their ID instead.

When uploading/downloading large amounts of files, it is advisable to save the log messages to a file. 
This can be done by appending `2> >(tee acd.log >&2)` to the command.

When the script is done running, its exit status can be checked for flags. If no error occurs, the exit status 
will be 0. The flag values are: 
argument error -- 2,
failed file transfer -- 8,
upload timeout -- 16,
hash mismatch -- 32,
error creating folder -- 64.
If multiple errors  occur, their values will be compounded by a binary OR operation.

##Usage example

```
$ ./acd_cli.py sync
# Syncing... Done.
$ ./acd_cli.py tree
# [PHwiEv53QOKoGFGqYNl8pw] [A] /
$ ./acd_cli.py create /egg/
$ ./acd_cli.py create /egg/bacon/
$ ./acd_cli.py upload local/spam/ /egg/bacon/
# Current directory: local/spam/
# Current file: local/spam/sausage
# [##################################################] 100.00% of 20.0MiB
# Current file: local/spam/lobster
# [##################################################] 100.00% of 10.0MiB
# [...]
$ ./acd_cli.py tree
# [PHwiEv53QOKoGFGqYNl8pw] [A] /
# [         ...          ] [A] /egg/
# [         ...          ] [A] /egg/bacon/
# [         ...          ] [A] /egg/bacon/spam/
# [         ...          ] [A] /egg/bacon/spam/sausage
# [...]
```

##Known Issues

 * files larger than 10GiB may not be downloaded
 * the tree and recursive folder listings are prone to infinite recursion if folder loops exist

Feel free to use the bug tracker to add issues. You might find the `--verbose` and `--debug` options helpful. 

##Dependencies

 * dateutils
 * pycurl
 * requests >= 1.0.0
 * sqlalchemy

If you are using a Debian-based distribution, the necessary packages are ``python3-dateutil python3-pycurl python3-requests python3-sqlalchemy``.

##Contact

acd_cli@mail.com

##Changelog

### Version 0.1.3
 * OAuth now via Appspot; security profile no longer necessary
 * back-off algorithm for API requests implemented

### Version 0.1.2
new:
 * overwriting of files
 * recursive upload/download
 * hashing of downloaded files
 * clear-cache action

fixes:
 * remove-child accepted status code
 * fix for upload of files with Unicode characters
 
other:
 * changed database schema
