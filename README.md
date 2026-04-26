# FlowFiles-app
Importing and visualizing Flow Files data


# Background
OE needs to process so-called “flow” files in order to communicate with the energy
industry. These are pipe-delimited text files that are sent to us via sFTP. Our
systems then import each file into our database.
There are lots of different types of flow files but, for this project, we are only
concerned with the “D0010” files which contain information about meter readings.
We need a new service that can import these files and allow their information to be
browsed via the web by support staff. For this challenge, files will be imported via
the command-line but, later on, a REST interface could be added to allow files to be
uploaded via the web.

# Application requirements
The application should be a Django project that runs on Python 3.10 or above.
It should have a management command that can be called with the path to a
D0010 file (or files). The relevant data for each meter-point should be extracted
and stored in a local database. The specification for these files is included below.
It should provide a version of the Django admin site that allows a user to search for
the reading values and dates associated with either:
● An MPAN
● A meter serial number
It should also be possible to see the filename of the flow file that the reading came
in.
There should be a test suite and instructions on how to run the tests.
Create an example D0010 file to test

## Supported File Types

The application supports D0010 flow files with the following extensions:
- **`.txt`** - Simple ZPT format (ZPT lines with complete reading data)
- **`.flo`** - Grouped format (026/028/030 lines)

The parser automatically detects and handles both formats.

## Key Features

- ✅ **Web-based File Upload**: Import files directly through the admin interface
- ✅ **Command-line Import**: Batch import files using management commands
- ✅ **Multiple Format Support**: Handles both simple ZPT and grouped 026/028/030 formats
- ✅ **Automatic Format Detection**: No need to specify format - it's detected automatically
- ✅ **Automatic Date Stamping**: Import date is automatically recorded
- ✅ **Duplicate Prevention**: Prevents importing the same file twice
- ✅ **Smart Error Handling**: Skips invalid rows while importing valid ones
- ✅ **Comprehensive Logging**: All operations logged to files and console
- ✅ **Search & Filter**: Search by MPAN or meter serial number
- ✅ **Complete Test Suite**: 26 tests covering all functionality including both formats

