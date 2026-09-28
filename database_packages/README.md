# Make a report from your Python script

A package contains your Python and the settings for its input form. **You edit
Python; RobotControl handles the form settings and ZIP.**

## Recommended: create it in RobotControl

1. Open **Database → Manage packages → Create report → Upload Python**.
   RobotControl detects ordinary imports, including imports inside functions. It
   lists bundled libraries and anything that needs manual attention without running
   the file. **Try an example** demonstrates the same flow without SQL setup.
2. In **Data and inputs**, choose connections and add the fields users need. Use
   **Configure connections** if this is your first report. Package IDs, versions and
   manual library overrides are under **Details**; source aliases are under
   **Source names in Python**.
3. If the script already supplies `run(context, inputs)`, it can proceed directly.
   Otherwise download the starter, keep your calculations and adapt the connection,
   input and output handling. Upload the completed `handler.py`. Your draft retains
   its form settings while you edit outside RobotControl, with or without a coding agent.
4. **Try report**, check the Excel output, then **Install** here or **Export package**
   for another installation. A successful trial does not establish calculation accuracy.

### Set up a connection once

Open **Database connections**, enter a name, server and database, then choose:

- **Create read-only account:** name a new SQL login, choose **Review access**, check
  the database and grants, and supply SQL administrator credentials for **Create account**.
  Alternatively, use the Windows identity running RobotControl if it has the required
  SQL authority. Setup credentials are used once and are not saved. The generated
  reader password is encrypted locally. This grants CONNECT, SELECT and VIEW DEFINITION
  on the named database, including future tables; existing SQL accounts are never changed.
- **Use existing account:** enter the credentials your lab provides. Choose
  **Read-only: viewers and reports** or **Operations: database changes**. The latter
  must not be used for reports. **Check and save** verifies the supplied access.

If you do not have SQL authority, download the reviewed SQL for your administrator.
They replace the password placeholder and run it, then give you the reader credentials
for **Use existing account**. The Microsoft ODBC driver must be installed on the host;
Python and UV are not needed on the deployment computer.

For an operation, choose its **Connections → Operation target** after installing it.
Existing operations also need this explicit assignment after this upgrade. Table and
procedure viewers have their own **Database connection** selector. Report packages
retain their source mappings. None of these choices redirects robot functions or Restore.

The wizard does not translate arbitrary Python calculations. Your handler implements
`run(context, inputs)`, uses `context.connections['source-name']`, writes Excel under
`context.output_dir`, and returns its filename. For example, a Plate dropdown sends
the selected ID as `inputs['plate_id']`; its displayed label is not passed to Python.

For database dropdowns, **Build from columns** creates a simple SELECT. For filtered
choices, return columns named `value` and `label`, use `?` for each parent value, and
select those parents in parameter order. Example:

```sql
SELECT PlateID AS value, PlateName AS label FROM dbo.Plates WHERE ProjectID = ?
```

Choose `project_id` under **Depends on**. Changing Project clears Plate. Choose the
correct value type (integer for an integer ID). No experiment table is required.

Use **Save and close**, then **Resume** to continue later. Drafts belong to their
author. To update, resume the draft, keep its package ID, increase the version and
upload the edited handler. Review installation before replacing the working report.

Connection passwords stay on this computer and are not exported with settings.
Installation on another computer needs local source assignments. Existing reports,
including Culture history, need **Connections → primary** assigned once after the
application upgrade; generation is blocked until configured. No write connection
is used as a fallback. Reviewed Python remains required; this is not a code sandbox.

Already have a ZIP? Use **Database → Manage packages → Add package**, or **Update**
beside the installed package. You do not need the steps below just to install it.

## Alternative: command-line authoring

Keep this route for existing source folders and database operations. These commands
require Python/UV on the development PC; the wizard and installed reports do not.

### 1. Create a working folder

On your development PC, open PowerShell in the RobotControl repository:

```powershell
cd C:/Users/Hamilton/Desktop/RobotControl
uv run --locked python build_scripts/database_package.py create ../MyDatabasePackages/my-report --script C:/Scripts/Data.py
```

Replace `C:/Scripts/Data.py` with your script's path; put quotes around it if it
contains spaces. The new `my-report` folder must not already exist.

For a report that asks the user to select an experiment, answer:

| Prompt | Enter |
| --- | --- |
| Name shown in RobotControl | `My culture report` |
| Stable package ID | `my-report` |
| Type | `report` |
| Version | `1.0.0` |
| Libraries | `pandas,openpyxl,pyodbc` |
| Input | `experiment_id:experiment:Experiment` |
| Next Input | Press Enter without typing anything |

The input line means: give Python a value named `experiment_id`, let the user
select an experiment, and label that control **Experiment**.

The helper creates `C:/Users/Hamilton/Desktop/MyDatabasePackages/my-report`:

- **handler.py:** the Python file you will edit.
- **manifest.json:** settings generated from your answers.
- **reference/Data.py:** an untouched copy of your original script.
- **AGENTS.md:** adaptation instructions for you or a coding agent.

**This creates a starting folder. It does not convert your original script.**

### 2. Finish handler.py

Keep your calculations, record-selection rules and workbook formatting. Change
how the script receives its input, connection and output location:

| Standalone script | Inside `run(context, inputs)` in handler.py |
| --- | --- |
| Reads an experiment from command-line arguments | Read `inputs["experiment_id"]` |
| Opens its own database connection | Use `context.connection` |
| Writes to a fixed Excel path | Save to `context.output_dir / "report.xlsx"` |
| Ends after saving | Return `"report.xlsx"` |

Move the relevant functions from the original into `handler.py`; do not simply call
its standalone `main()`. RobotControl calls `run(context, inputs)` for you.

You can do this yourself, or give a coding agent this request:

> Open C:/Users/Hamilton/Desktop/MyDatabasePackages/my-report. Read AGENTS.md and
> the original script in reference/. Complete handler.py for RobotControl. Preserve
> the calculations, record selection and Excel formatting. Use the supplied database
> connection and experiment input. Explain uncertainty before changing report
> behavior. Check the result with disposable data.

When the adapter is complete, remove its `ADAPT_BEFORE_BUILD` comment. Removing the
comment alone does not finish the code.

## 3. Build the ZIP

From the same RobotControl repository:

```powershell
uv run --locked python build_scripts/database_package.py build ../MyDatabasePackages/my-report
```

This produces `C:/Users/Hamilton/Desktop/MyDatabasePackages/my-report-1.0.0.zip`.
It checks package structure and Python syntax; it does not prove calculations are
correct. If it reports an unfinished adapter, go back to step 2.

## 4. Install and check the report

1. Open **Database → Manage packages → Add package**.
2. Choose `my-report-1.0.0.zip`, review the name/version, then install.
3. Open **Database → Data retrieval** and choose **My culture report**.
4. Select an experiment from disposable data, generate Excel and check its contents.

Keep the `my-report` source folder. You will edit it for future updates.

### Update your command-line project later

Edit the existing `handler.py`; **do not run create again**. Then build a new version:

```powershell
uv run --locked python build_scripts/database_package.py build ../MyDatabasePackages/my-report --version 1.0.1
```

Click **Update** beside My culture report and choose `my-report-1.0.1.zip`.
Keep its package ID unchanged so RobotControl recognizes the update.

Python and UV are needed on the development PC for these commands, not on the
robot's deployment PC. Updating the RobotControl executable does not replace an
already installed report; update the report's ZIP separately.

For operations that change data, other input types, libraries and limits, see the
[technical reference](CONTRACT.md).
