acd_cli
=======

**acd_cli** aims to provide a command line interface to Amazon Cloud Drive written in Python 3. It is currently in alpha stage.

##Features

 * local node caching
 * addressing of nodes via a pathname (e.g. `/Photos/kitten.jpg`)
 * tree listing of files and folders
 * upload/download of single files 
 * background hashing
 * folder creation
 * trashing/restoring
 * moving nodes

##Planned

 * recursive upload/download
 * folder syncing
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
    sync                refresh node cache
    clear-cache         clear the node cache
    tree                print directory tree
    upload              upload a file
    download            download a remote file
    create              create folder
    trash               move to trash
    restore             restore from trash
    children            list folder's children
    move                move node A into folder B
```
And some more
```
    resolve             resolve a path to a node id
    add-child           add a node to a parent folder
    remove-child        remove a node from a parent folder
    usage               show drive usage data
    quota               show drive quota
    metadata            print a node's metadata
    changes             list changes
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
# 1 folder(s) inserted.
$ ./acd_cli.py create /egg/bacon/
# 1 folder(s) inserted.
$ ./acd_cli.py upload local/spam /egg/bacon/
# [##################################################] 100.00% of 20.0MiB
# 1 file(s) inserted.
$ ./acd_cli.py tree
# [PHwiEv53QOKoGFGqYNl8pw] [A] /
# [MaBngd6VTByJunX-8zeWMg] [A] /egg/
# [uPbjGFCqRGi-wFJTOV8ggQ] [A] /egg/bacon/
# [m2lCXyDCTZeeYWxZXCbAsA] [A] /egg/bacon/spam
$ ./acd_cli.py move /egg/bacon/spam /
# 1 file(s) updated.
```


##Known Issues

 * Nodes with multiple parents might mess up the cache

Feel free to use the bug tracker to add issues.

##Dependencies
* pycurl
* requests
* sqlalchemy
* dateutils

##Changelog
=========

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