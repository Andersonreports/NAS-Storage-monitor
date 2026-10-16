# NAS Storage Monitor

Dashboard for the two NAS drives: total/free space, usage per user, and day-wise history.
Pure Python 3 standard library, so there's nothing to `pip install`.

Live page: https://andersonreports.github.io/NAS-Storage-monitor/

| File | Purpose |
|---|---|
| `index.html` | The dashboard: landing page plus one module page per NAS. Reads `data.json`. |
| `collector.py` | Scans each NAS mount and saves today's numbers to SQLite (`data/storage.db`). Run once a day. |
| `import_transfer.py` | Imports a department transfer-status sheet (CSV in `imports/`) for a NAS. |
| `export.py` | Writes `data.json` from the database; commit it to update the GitHub Pages copy. |
| `server.py` | Serves the dashboard on the office network with live data (port 8080). |
| `config.json` | NAS names, mount paths, capacity, how users are detected, alert thresholds. |
| `seed_demo.py` | Sample data for any NAS marked `"demo": true` (currently NGS NAS). |

## 1. Update the data (no commands needed)

Open a NAS page on the dashboard and use the buttons at the top right.

**Live sheet (recommended, everyone sees it).** Connected sheet: [NAS STORAGE](https://docs.google.com/spreadsheets/d/1m4-yM4mn1kzAbfCiYznvXrwgx8yUc-Wm9gTus6LHDd8/edit),
tab **CMC** → CMC NAS, tab **NGS** → NGS NAS. Starter contents for each tab are in `sheet_templates/`.
Don't delete or recreate the tabs: the dashboard finds them by tab ID.

 Keep the transfer status in a Google Sheet with the same
columns as the report (`Department`, `Dest. share`, `Checked?`, `Samples`, … `Size (GB)`, `Copied (GB)`, `Pending (GB)`).
- Share it as *Anyone with the link can view*, or use *File → Share → Publish to web → CSV*.
- Put the link in `config.json` as `"sheet_url"` for that NAS. You can edit the file on github.com with the pencil icon.
  The dashboard reads the sheet each time someone opens it.
- For day-wise history in one sheet, add a `Date` column and append each day's rows. Otherwise put
  "As of 14-Oct-2026 06:41" above the header; each new date adds a point to the history.
- The **Live sheet** button connects a sheet in your own browser only, which is useful for trying it first.

**Upload Excel.** Choose the report `.xlsx` / `.csv`. The dashboard reads the "As of …" date and the department
table and adds it to the history. Uploads are kept **in that browser only**, so other people (for example your TL)
won't see them. Use the live sheet to share.

Staff names written as "Haematology - Name" are shown as "Haematology - user1" (the destination share),
because the page is public.

Set `capacity_bytes` for CMC NAS in `config.json` (for example `35184372088832` for 32 TB) to turn on
% used, free space and the days-until-full projection.

### Command-line alternative

```bash
python3 import_transfer.py --nas "CMC NAS" --at "2026-10-07 06:41" imports/cmc_transfer_2026-10-07.csv
python3 export.py && git add data.json imports && git commit -m "Update storage data" && git push
```

## 2. Mount the NAS shares (read-only is enough)

SMB/CIFS (Synology, QNAP, Windows shares):

```bash
sudo apt install cifs-utils
sudo mkdir -p /mnt/nas1 /mnt/nas2
# /etc/fstab
//192.168.1.10/share  /mnt/nas1  cifs  ro,credentials=/etc/nas-cred,iocharset=utf8,vers=3.0  0  0
//192.168.1.11/share  /mnt/nas2  cifs  ro,credentials=/etc/nas-cred,iocharset=utf8,vers=3.0  0  0
# /etc/nas-cred  (chmod 600) -> username=...\npassword=...
sudo mount -a
```

NFS: `192.168.1.10:/volume1/share  /mnt/nas1  nfs  ro  0 0`

Use an account that can **read every user's folder**, or those folders are counted
as unreadable (shown in the collector output).

## 3. Edit `config.json`

- `path`: the mount point. Total/used/free come from here.
- `user_mode`:
  - `"folders"` (default): every top-level folder under `user_root` is one user
    (for example `/mnt/nas1/homes/alice`). Set `user_root` to `/mnt/nas1/homes` for Synology home folders,
    or leave it as the share root to see usage per department or share folder.
  - `"owner"`: groups files by the owner on disk. Only useful on NFS or SMB mounts that keep real Unix
    ownership; on a normal CIFS mount every file looks like it belongs to the mounting user.
- `exclude`: folder names to skip (recycle bins, snapshots, thumbnails).
- `thresholds`: % used at which a NAS shows Warning / Critical.

## 4. Run the collector daily

```bash
python3 collector.py          # test it once by hand
crontab -e
30 1 * * * cd /home/anderson/Projects/NAS-Storage-monitor && /usr/bin/python3 collector.py >> data/collector.log 2>&1
```

A scan walks every file, so it can take minutes to hours on a big NAS. Night time is best.
Running it again on the same day overwrites that day's data.

## 5. Keep the dashboard running (systemd)

```ini
# /etc/systemd/system/nas-dashboard.service
[Unit]
Description=NAS Storage Dashboard
After=network-online.target

[Service]
WorkingDirectory=/home/anderson/Projects/NAS-Storage-monitor
ExecStart=/usr/bin/python3 server.py
User=anderson
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now nas-dashboard
```

Then open `http://<this-machine-ip>:8080` from any PC on the network.
The dashboard has no login, so keep it on the internal network only.
