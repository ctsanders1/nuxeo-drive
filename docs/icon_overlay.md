# GNU/Linux

## Nautilus

Install required Nautilus addons:

    sudo apt install python-nautilus nautilus-emblems

Create custom emblems:

    mkdir -p ~/.icons/hicolor/48x48/emblems
    cp nxdrive/data/icons/overlay/nautilus/* ~/.icons/hicolor/48x48/emblems

Install the extension:

    cp nxdrive/overlay/nautilus/file_info_updater.py ~/.local/share/nautilus-python/extensions

# macOS

There is nothing to do. The `FinderSync` plugin will be lauched when Nuxeo Drive starts.

The revelant source code can be found in `tools/osx/drive` and `nxdrive/osi/darwin` folders.

# Windows

The icons overlay is implemented as a Windows callback service as described in the [official documentation](https://msdn.microsoft.com/en-us/library/windows/desktop/cc144122(v=vs.85).aspx).

The revelant source code can be found in the `tools/windows/setup.iss` file and the `nxdrive/osi/windows` folder.

## Limitation

There is a known limitation on the Windows side that [restricts the number of icon overlays to **15**](https://superuser.com/a/1166585/180383) (see also [Image Overlays on MSDN](https://msdn.microsoft.com/en-us/library/windows/desktop/bb761389%28v=vs.85%29.aspx#Image_Overlays)).
That limitation cannot be bypassed and Microsoft never communicated on the subject about a possible future removal or increase.

Let's say there are installed softwares like NextCloud, Dropbox, Google Drive, OneDrive, ...
Only the 15th first registry entries in `HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers` will be taken into account.

And so, it is an open war for whom will be the 1st listed by adding spaces in the begining of the key name. For instance, [as of 2017-01-17](https://stackoverflow.com/q/41697737/1117028), Dropbox is adding 3 spaces before its name to be 1st.
Nuxeo will not take part of that endless war, we are simply adding key names like `Drive_action`.

To be crystal clear: the more synchronization software you have, the lesser chance you have to see Nuxeo Drive icons.

If you are in the bad situation like above, your only option is to remove or rename other softwares registry keys like described here: [Making Icon Overlays Appear In Windows 7 and Windows 10](https://www.interfacett.com/blogs/making-icon-overlays-appear-in-windows-7-and-windows-10/).
