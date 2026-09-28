# Make a report from your Python script

A package is a ZIP containing your Python code and the settings RobotControl needs
to display its input form. **You edit the Python; the helper builds the ZIP.**

Already have a ZIP? Use **Database → Manage packages → Add package**, or **Update**
beside the installed package. You do not need the steps below just to install it.

## 1. Create a working folder

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

## 2. Finish handler.py

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

## Update your report later

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
