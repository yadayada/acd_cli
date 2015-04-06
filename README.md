acd_cli
=======

**acd_cli** aims to provide a command line interface to Amazon Cloud Drive written in Python 3. It is currently in alpha stage.

##Features

 * node caching
 * mapping of node IDs to a "remote" path
 * tree listing of files and folders
 * upload/download of single files 
 * folder creation
 * trashing/restoring
 * moving nodes

##Planned

 * recursive upload/download
 * folder syncing
 * processing of incremental changes
 * ... minor stuff

##Quick start
If you have not done so already, register a security profile with Amazon and whitelist your App. Refer to https://developer.amazon.com/public/apis/experience/cloud-drive/content/getting-started for further details.

Enter your client credentials into the JSON file named `client_data`. You will have to complete the OAuth procedure one time.

##Usage

The following actions are built in

```
    sync                refresh node list cache
    tree                print directory tree
    upload              upload a file
    download            download a remote file
    create              create folder
    trash               move to trash
    restore             restore from trash
    children            list folder's children
    move                move node A into folder B
    resolve             resolves a path to a node id
    add-child           add a node to a parent folder
    remove-child        remove a node from a parent folder
    usage               show drive usage data
    quota               show drive quota
    metadata            print a node's metadata
    list-changes        list changes
```

Please run ```./acd_cli.py --help``` to get a current list of the available actions and help on further arguments.

You may provide any node argument as a 22 character ID or a UNIX-style path. Directories must always end with a forward slash '/'. 

##Usage example

```bash
$ ./acd_cli.py sync
# Syncing... Done.
$ ./acd_cli.py tree
# [PHwiEv53QOKoGFGqYNl8pw] [A] /
$ ./acd_cli.py create /egg/
# [...]
# 1 folder(s) inserted.
$ ./acd_cli.py create /egg/bacon/
# [...]
# 1 folder(s) inserted.
$ ./acd_cli.py upload local/spam /egg/bacon/
# [##################################################] 100.00% of 20.0MiB
# [...]
# 1 file(s) inserted.
$ ./acd_cli.py tree
# [PHwiEv53QOKoGFGqYNl8pw] [A] /
# [MaBngd6VTByJunX-8zeWMg] [A] /egg/
# [uPbjGFCqRGi-wFJTOV8ggQ] [A] /egg/bacon/
# [m2lCXyDCTZeeYWxZXCbAsA] [A] /egg/bacon/spam
$ ./acd_cli.py move /egg/bacon/spam /
# [...]
# 1 file(s) updated.
```


##Known Issues

Downloaded files are not being hashed currently.

##Dependencies
* pycurl
* requests
* sqlalchemy