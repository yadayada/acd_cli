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
 * shell completion
 * processing of incremental changes
 * ... minor stuff

##Quick start
If you have not done so already, register a security profile with Amazon and whitelist your profile for the Cloud Drive API. Refer to https://developer.amazon.com/public/apis/experience/cloud-drive/content/getting-started for further details.

As this is a local application, your security profile must include ``http://localhost`` as an allowed return url.
If you select your profile in the the 'Security Profile Management' (https://developer.amazon.com/iba-sp/overview.html), this setting can be found in the 'Web Settings' tab, named 'Allowed Return URLs'.

Enter your security profile's client credentials ('Client ID' and 'Client Secret') into the JSON file named `client_data`. 

On the first start of the program (try ``./acd_cli.py sync``), you will have to complete the OAuth procedure.
You will be asked to visit a URL, log into Amazon and paste the URL that you have been redirected to into the console.


##Usage

The following actions are built in

```
    sync (s)            refresh node list cache; necessary for many actions
    clear-cache (cc)    clear node cache
    tree (t)            print directory tree [uses cached data]
    upload (ul)         file and directory upload to a remote destination
    overwrite (ov)      overwrite node A [remote] with file B [local]
    download (dl)       download a remote file; will overwrite local files
    create (c, mkdir)   create folder
    list-trash (lt)     list trashed nodes [uses cached data]
    trash (tr)          move to trash
    restore (re)        restore from trash
    children (ls)       list folder's children [uses cached data]
    move (mv)           move node A into folder B
    rename (rn)         rename a node
```
And some more
```
    resolve (rs)        resolve a path to a node id
    add-child           add a node to a parent folder
    remove-child        remove a node from a parent folder
    usage               show drive usage data
    quota               show drive quota
    metadata            print a node's metadata
    changes             list changes
```

Please run ``./acd_cli.py --help`` to get a current list of the available actions. You may also get a list of  further arguments and their order of an action by calling ``./acd_cli.py [action] --help``.

You may provide most node arguments as a 22 character ID or a UNIX-style path. Trashed nodes' paths might not be able to be resolved correctly; use their ID instead.

##Usage example

```bash
$ ./acd_cli.py sync
# Syncing... Done.
$ ./acd_cli.py tree
# [PHwiEv53QOKoGFGqYNl8pw] [A] /
$ ./acd_cli.py create /egg/
$ ./acd_cli.py create /egg/bacon/
$ ./acd_cli.py upload local/spam/ /egg/bacon/
#Current directory: local/spam/
#Current file: local/spam/sausage
# [##################################################] 100.00% of 20.0MiB
#Current file: local/spam/lobster
# [##################################################] 100.00% of 10.0MiB
#[...]
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
* pycurl
* requests
* sqlalchemy
* dateutils

##Changelog

## Version 0.1.2
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
