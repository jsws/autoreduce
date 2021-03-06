# Autoreduction Web App Technical Documentation

## Overview
The autoreduction web app is a user interface for the autoreduction system that takes experiment data and runs it through a reduction script without the need for user prompt. This interface is made available through a web browser, on any internet connected device, and gives the status of reduction jobs that have been submitted. It also provides the ability to change variables and re-run experiment data with new variables and/or reduction script.

## Contents

1. [Overview](#overview)
2. [Technologies](#technologies)
    1. [Django](#django)
    2. [ActiveMQ](#activemq)
    3. [Stomp.py](#stomppy)
    4. [MySQL](#mysql)
    5. [JavaScript](#javascript)
    6. [CSS](#css)
3. [Components](#components)
    1. [autoreduce_webapp](#autoreduce_webapp)
    2. [reduction_viewer](#reduction_viewer)
    3. [reduction_variables](#reduction_variables)
4. [Templates](#templates)
5. [Managing the Services](#managing_the_services)
    1. [Autoreduction Backend](#autoreduction_backend)
    2. [Autoreduction Webapp](#autoreduction_webapp)
    3. [MySQL Database](#mysql_database)
6. [Tests](#test)
7. [Other Notes](#other-notes)
9. [Possible Problems & Solutions](#possible-problems-&-solutions)

## Technologies

### [Django](https://www.djangoproject.com/)
**Version:** 1.7

Web framework for python. Abstracts away various tasks such as database access, logging, admin interface, templating and URL routing. The web server proxies request through to Django (via wsgi with Apache or fcgi with IIS) that then handles loading the correct files, managing errors, etc.

**Updating:** Django is installed through `pip` or `easy_install`. Update using these tools for best results. Make sure to check https://docs.djangoproject.com/en/1.7/releases/ for any breaking changes before updating.

### [ActiveMQ](http://activemq.apache.org/) 
**Version:** 5.11.1

ActiveMQ is a messaging server that supports publish/subscribe to both queues and topics. It handles multiple protocols but only Stomp is being used in this web app. It should be ensured that the server is restricted to SSL and with credentials (See installation instructions).

### [Stomp.py](https://github.com/jasonrbriggs/stomp.py)
**Version:** 4.0.12

Stomp.py is a python client for communicating with messaging servers using the Stomp protocol.

### [MySQL](http://www.mysql.com/)
**Version:** 5.6.21

Database to store all information about the web app (users, reduction runs, notifications).

### JavaScript
**Third Party Libraries:**
* [JQuery](http://jquery.com/) - Utility library to make DOM manipulation, event handling, etc. easier and more cross-browser compatible.
* [Bootstrap v3.3.0](http://getbootstrap.com/) - Layout interaction and components (such as dropdown menus, modal windows, etc.)
* [Bootstrap-Switch](http://www.bootstrap-switch.org/) - Provides a toggle script for the instrument variables page.
* [FastDOM](https://github.com/wilsonpage/fastdom) - Allows for better handling of multiple DOM manipulations. Prevents [layout thrashing](http://wilsonpage.co.uk/preventing-layout-thrashing/).
* [Prettify](https://code.google.com/p/google-code-prettify/) - Provides syntax highlighting for the script preview window.

**Notes:** 
* **polyfills.js** - This file provides some often used features that are missing from some browsers. These include functions such as `startsWith` and `endsWith` for strings.
* **cookies.js** - Easier saving and reading of cookies taken from https://developer.mozilla.org/en-US/docs/Web/API/document.cookie.
* All other JavaScript files have their code wrapped in a [IIFE](http://benalman.com/news/2010/11/immediately-invoked-function-expression/) (Immediately-Invoked Function Expression) to prevent polluting the global scope with variables that could possibly conflict. All have a single `init()` function that is called on page load, this function handles any initialisation that is needed, such as hooking up event handlers.

### CSS
**Third Party Libraries:**
* [Bootstrap](http://getbootstrap.com/) - Layout interaction and components (such as dropdown menus, modal windows, etc.) and provide a grid layout to make responsive layout much easier.
* [Prettify](https://code.google.com/p/google-code-prettify/) - Provides syntax highlighting for the script preview window.
* [Font Awesome](http://fortawesome.github.io/Font-Awesome/) - Icon Font used for the icons on the sight to make them scalable and clear on all displays.





## Components

The web application is split into 3 components, known as apps in Django. These are:
* autoreduce_webapp
* reduction_viewer
* reduction_variables





### autoreduce_webapp
This is the core of the web app. It handles the application-wide settings, utilities and services.

#### settings.py
This contains the settings for all three components, most importantly credentials - `ACTIVEMQ` and `ICAT` - and data directories for reduction - `REDUCTION_DIRECTORY` and `ARCHIVE_DIRECTORY`.
It also contains the settings for Django itself.


#### queue_processor.py
The `queue_processor.py` isn't strictly part of the web application but runs separately as a service but makes use of the modules made available by autoreduce_webapp (such as models and utilities). This contains a Stomp Client and Listener that sits and listens for messages from ActiveMQ on the following queues:
* `/queue/DataReady`
* `/queue/ReductionStarted`
* `/queue/ReductionComplete`
* `/queue/ReductionError`

When it retrieves a message from one of these queues it inspects the message (a [JSON](http://www.json.org/) object) and, depending on the queue the message was from, updates the database with the details it finds.

This actions this script takes are:
* `DataReady` - Create a new ReductionRun record representing the data that has come off the instrument. This then sends a message to the `/queue/ReductionPending` queue for it to be picked up by the autoreduction service.
* `ReductionStarted` - This simply updated the status of the saved ReductionRun to note that the reduction job is now being performed by the autoreduction service.
* `ReductionComplete` - This updates the status, logs and performs post-processing. ICAT is updated with the reduction details. The reduced data is checked for .png files and these converted to a [base64](http://css-tricks.com/data-uris/) encoded string and saved in the database to be shown via the web application.
* `ReductionError` - This logs the error that was retrieved and updated the status and logs of the ReductionRun. If the run should be retried, it will schedule a retry.

When using the `Client` there are some optional arguments that could cause problems is not correctly set.
`topics` - a list stating what queues/topics to subscribe to (Default: None)
`client_only` - Set this True if you only require sending a message to the message queue (for example in `MessagingUtils.send_pending`).
`use_ssl` - This needs to be set to True is connecting to the messaging queue over SSL (recommended). (Default: False)
`ssl_version=3` - Dependent on what version of Java is being run, but the default is considered to have security issues which using TLS fixes.

#### icat_communication.py

This handles all communication to [ICAT](http://icatproject.org/) and acts as a wrapper to the icat python client. 

This is used in two ways. 

The first uses the credentials store in the `settings.py` file of autoreduce_webapp. This user should have elevated permissions and so this method is used for activities such as getting all upcoming experiments for an instrument and running the tests.
```python
with ICATCommunication() as icat_client:
    # icat_client.do_something()
```
The second passes in the current users session ID. This should be used for most calls as it will correctly filter results based on the permission of the user and on what they are associated with.
```python
with ICATCommunication(AUTH='uows',SESSION={'sessionid':request.session.get('sessionid')}) as icat:
    # icat_client.do_something()
```

ICATCommunication also supports more overrides passed in as kwargs but aren't currently used outside of tests. 

```python
ICATCommunication(URL='',AUTH='',SESSION={},USER='',PASSWORD='')
```

ICATCommunication will logout of ICAT when it goes out of the scope of the `with` statement.

#### icat_cache.py

This wraps ICATCommunication, implementing a cache mechanism that stores query results. It's intended to be used exactly as ICATCommunication would be (i.e., in a `with` statement).

The setting `CACHE_LIFETIME` (in seconds) controls how long objects live in the cache. If ICATCache finds a cache object that's younger than this setting in the database, it will use that instead of going to ICATCommunication. Otherwise, it will try to connect to ICAT via ICATCommunication and make the query, storing it to the cache. If this fails somehow, it'll return the stale cache object if there is one, or else return `None`.

#### uows_client.py

This handles communication with the User Office Web Service to handle authentication and retrieving user details.

It provides 3 method: `check_session`, `get_person` and `logout`, all which take in the users current session ID. 

`get_person` returns a trimmed-down version of the details stored in the User Office system. (first name, last name, email and usernumber)

The UOWSClient can be called with an optional kwarg parameter that sets the URL of the web service which defaults to what is stored in the `settings.py` of autoreduce_webapp.

```python
with UOWSClient(URL='') as uows_client:
    # uows_client.do_something()
```

#### backends.py

This contains custom backend functions. Backends are things such as authentication and database access.

Currently there is a single custom backend, `UOWSAuthenticationBackend`, that provides authentication via the User Office system.

UOWSAuthenticationBackend provides a `authenticate` function that takes in a session ID and verifies it's valid using uows_client.py. If valid it then checks if an associated user account exists in the local MySQL database, creating one if none is found. This function also calls ICAT to update the users permission status (whether they are staff or superuser/admin) 

#### utils.py

Provides application-wide utilities. Contains `SeparatedValuesField` that can be used by models to implement a list/array-like field property. Values are stored in the database as text separated by the pipe character (|). This is currently only used by ReductionRun to store graphs.

#### view_utils.py

Provides application-wide function decorators for view methods. These include things like checking a session ID is still valid (`login_and_uows_valid`) or that a user is a staff memeber (`require_staff`). `require_staff` and `require_admin` will both throw a [403 Forbidden](http://en.wikipedia.org/wiki/HTTP_403) is the current user doesn't have the appropriate permissions. If not logged in, the user will be redirected to the login page first.

`check_permissions` is used for general-purpose permissions checking; it looks at the keyword arguments of the function, and checks that the user has access to the run/instrument/experiment that's being looked at, checking ICATCache for the permissions.

The main function worth taking note of is `render_with`. This is used by all view functions except those that are called from within another view (as these don't trigger function decorators). When used, this expect the function to return a dictionary (the context dictionary that will be used by the template) which it then adds any active notifications, flags and values such as support email and then calling the `render_to_response` on the appropriate template file with the dictionary fully populated. This means there is a single location to put all context variables that are needed on all (or most) pages without having to add it to each view function.

Example:
```python
@render_with('template_name.html')
```

#### templatetags

The templatetags directory contains custom filters and tags that can be used within templates. These need to be loaded in the same was as built in [Django tags/filters](https://docs.djangoproject.com/en/1.7/ref/templates/builtins/):
```
{% load colour_table_rows %}
```

* **colour_table_rows.py** - Takes in the status of a ReductionRun and returns back the appropriate Bootstrap colour class.
* **get_user_name.py** - Takes in a usernumber and returns back a mailto link with the users full name.
* **natural_time_difference.py** - Takes in a start and end datetime and returns back a duration in days, hours, minutes and seconds where appropriate.
* **replace.py** - Replaces all occurrences of a string with another in the given text.
* **variable_type.py** - Used by the edit variables forms to return the correct input type for values such as "list_number" or "boolean".
* **view.py** - Provides the ability to include a view function from within a template. Note: This doesn't trigger any middleware/function decorators on the view function.


### reduction_viewer

This contains most of the models and logic for the web app itself. Everything not related to run/instrument variables are found within this app. 

#### models.py

Models are the instances of database records. Each model matches against a table in the database.

* **Instrument** - A simple model containing the instrument name and whether it is active in the web app.
* **Experiment** - A record containing only the experiment reference number, used to link reduction runs together.
* **Status** - Status of the reduction run, either Queued, Processing, Completed, Skipped or Error.
* **ReductionRun** - The main model that contains most information about a reduction run job. 
    The important fields are
    * `run_number` - the integer ID for the data run that this is processing.
    * `run_version` - will begin at 0 for an initial reduction triggered when coming off the instrument, and will subsequently be greater if the run is a rerun (of another run with the same `run_number`).
    * `instrument` and `experiment` - referencing the instrument and experiment that this run is associated with.
    * `script` - a string of the `reduce.py` script that the run will be/was reduced with.
    * `status` and `message` - the `Status` of the run as above, and a string that will be displayed as, e.g., the failure message of the run if it has failed.
    * `retry_run` and `retry_when` - if this run has been scheduled to be retried, this will point to the new run, and the time at which it's scheduled to be processed.
* **DataLocation** - Stores the file path of the data for a reduction run.
* **ReductionLocation** - Stored the output directories of a completed reduction job.
* **Setting** - Key/Value pair of settings to be used throughout the web app and can be quickly and easily changed through the admin interface. Current settings are: `support_email`, `admin_email` and `ICAT_YEARS_TO_SHOW`.
* **Notification** - A model for showing notifications at the top of pages. These have various severities (info, warning and error) that determine the colour of the notification. It is possible to limit notifications to only be shown to staff using the `is_staff_only` boolean and notifications can be enabled/disabled by setting the `is_active` boolean. Some notifications are created and shown on-the-fly in the `view_utils.py` 

#### utils.py

This contains utilities related to the models found within reduction_viewer.

* **StatusUtils** - A helper function to get status models back for either Queue, Processing, Completed or Error. This utility wraps all calls in a `get_or_create` call to remove the need of pre-populating the database with these values.
* **InstrumentUtils** - A helper function to get Instrument models back for the provided name. If an instrument matching the name isn't found, one is created prior to return.
* **ReductionRunUtils** - Contains helper functions for `ReductionRun`s. `cancelRun()` provides cancellation functionality for runs that are being or will be retried. `createRetryRun()` 'copies' the provided run, suitable for retrying (e.g., it ensures that the `run_version` field is incremented as necessary).


#### views.py

This contains the source for some of the web pages and front-end functionality provided by the webapp. Functions which are run to render pages typically have a decorator of the form `@render_with('template.html')`. Notable pages include
* `run_queue()` - displays the pending/running jobs list.
* `fail_queue()` - displays the failed jobs list on GET, and handles actions sent to it (e.g., retry these jobs) on POST.
* `run_list()` - populates the front page with all the runs that the user can see.


### reduction_variables

All models and logic related to run/instrument variables are found within this app.

#### models.py
* **Variable** - The base class for reduction variables variables. Variables can either be standard or advanced, as indicated by the `is_advanced` boolean. This model isn't registered with Django in `admin.py`.
* **InstrumentVariable** - Stores variables for a single instrument with either a starting run number or an experiment reference number. 
* **RunVariable** - Stored variable for a specific run job; upon first reduction run version these will be populated by the matching instrument variables (based on either experiment reference number or run number, in that order). Re-run jobs will use the values the user enters, or the same ones as the previous run. 

#### utils.py

This contains utilities related to the models found within reduction_variables.

* **VariableUtils** - Contains utilities relating to individual variables. E.g. `wrap_in_type_syntax` takes in a value and adds the appropriate syntax around it to match the type provided. For example, a `1,2,3` with type of `list_number` would return `[1,2,3]` as a string to be used in the preview script.
* **InstrumentVariablesUtils** - Provides utilities for setting and fetching InstrumentVariables and scripts. Of particular note is the `create_variables_for_run` function that is [mentioned below](#selecting-run-variables) and `get_current_and_upcoming_variables` that is also [mentioned below](#upcoming-instrumentvariables). Methods of the form `show_` return copies of `InstrumentVariable`s given the conditions; `set_` will delete old `InstrumentVariable`s for the conditions and save the ones provided. All methods will keep variables with `tracks_script` set up to date when they're called.
* **MessagingUtils** - Contains `send_pending`, which takes in a ReductionRun and sends it to the messaging queue for processing (with an optional delay), and `send_cancel`, which sends the run to the queue processor to be cancelled if it is rerun.

#### views.py

This contains the source for the rest of the web pages and front-end functionality. Notable pages include
* `instrument_summary` and `instrument_variables`, which render the instrument view pages.
* `run_summary`, which is used to submit rerun requests from the summary page for a run, on POST.




## Templates

All templates use the [Django template language](https://docs.djangoproject.com/en/1.7/topics/templates/).

Templates are split into pages and snippets.

There is a `base.html` that all pages extend from. This contains the main structure of the page and the head. It includes multiple blocks that child pages can use to insert markup at the correct location (stylesheets, scripts, body etc.).

Pages can include imports (E.g. `{% load colour_table_rows %}`) that provide template tags and helpers. See the note above about [custom template tags](#templatetags).

Many pages also include snippets that are reused in multiple places. Snippets can be found in the `snippets` directory and contain just a small portion of markup with now `extends` tag. 

Example of using a snippet:
```
{% include "snippets/instrument_table.html" with instrument=instrument reduction_variables_on=reduction_variables_on by="experiment" user=user only %}
```

As shown above, snippets can be passed variables that will then be available in its scope. The final, optional, argument shown above, `only`, indicates that the snippet with only have access to the variables passed in an none of the rest of the page's context dictionary.

`header.html` - contains anything that needs to go at the top of every page. This includes the title and notifications.
`navbar.html` - contains the navigation bar that is shown at the top of every page.
`footer.html` - contains the help text shown at the bottom of every page.





## Managing the Services

### Autoreduction Backend

**Starting the service**

1. Log on to the autoreduction server
2. `su autoreduce`
3. `python /usr/bin/queueProcessor_daemon.py start`

**Stopping the service**

1. Log on to the autoreduction server
2. `su autoreduce`
3. `python /usr/bin/queueProcessor_daemon.py stop`

**Viewing Logs**

1. Log on to the autoreduction server
2. `su autoreduce`
3. For an updating log view: `tail -f /var/log/autoreduction.log`

### Autoreduction WebApp

**Starting the web app**

1. Remote desktop onto the reduce server
2. Open "Internet Information Services (IIS) Manager"
3. Expand the tree under "connections" until you see "Autoreduction"
4. Right-click "Autoreduction" -> Manage Website -> Start

**Stopping the web app**

1. Remote desktop onto the reduce server
2. Open "Internet Information Services (IIS) Manager"
3. Expand the tree under "connections" until you see "Autoreduction"
4. Right-click "Autoreduction" -> Manage Website -> Stop

**Starting the queue processor service**

1. Remote desktop onto the reduce server
2. Open "Services"
3. Right-click "Autoreduce Queue Processor" -> Start

**Stopping the queue processor service**

1. Remote desktop onto the reduce server
2. Open "Services"
3. Right-click "Autoreduce Queue Processor" -> Stop

**Viewing Logs**

1. Remote desktop onto the reduce server
2. Navigate to `C:\autoreduce\WebApp\ISIS\autoreduce_webapp`
3. Open `autoreduction.log`

### MySQL Database

**Starting the queue processor service**

1. Remote desktop onto the reduce server
2. Open "Services"
3. Right-click "MySQL" -> Start

**Stopping the queue processor service**

1. Remote desktop onto the reduce server
2. Open "Services"
3. Right-click "MySQL" -> Stop

**Viewing Logs**

1. Remote desktop onto the reduce server
2. Navigate to `C:\ProgramData\MySQL\MySQL Server 5.6\data`
3. Open `REDUCE.err`




## Tests

All tests are run using `manage.py test` from the root of the web application. Please see: https://docs.djangoproject.com/en/1.7/topics/testing/ for more info.

Tests are split across 3 files in the `test` directory, beginnig with `test_`. Each of these has sub-classes that split the tests up into testing different utilities (such as the queue processor). All test method names must begin with test.

```
python manage.py test test.test_autoreduce_webapp.QueueProcessorTestCase
```
```
python manage.py test test.test_autoreduce_webapp.ICATCommunicationTestCase
```
```
python manage.py test test.test_autoreduce_webapp.UOWSClientTestCase
```
```
python manage.py test test.test_reduction_variables.InstrumentVariablesUtilsTestCase
```
```
python manage.py test test.test_reduction_variables.VariableUtilsTestCase
```
```
python manage.py test test.test_reduction_variables.ReductionVariablesUtilsTestCase
```
```
python manage.py test test.test_reduction_variables.MessagingUtilsTestCase
```

Note: UOWSClientTestCase requires you enter a valid username and password for the User Office Web Service.




## Other Notes

### Before going live with app

To improve security: In the django settings.py generate a new `SECRET_KEY`. See: https://gist.github.com/ndarville/3452907.

### Expected message format

Messages that are sent to the ActiveMQ broker are send as JSON. And example of what is expected to be included is below:
```json
{
    'run_number' : 123456,
    'instrument' : 'GEM',
    'rb_number' : 1234567,
    'data' : '/path/to/data/',
    'reduction_script' : 'import module\nfor x in ...',
    'arguments' : { ... },
    'message' : 'Some form of feedback, possible an error message',
    'reduction_data' : ['/path/1', '/path/2']
}
``` 
`'reduction_script'` is a string of the reduction script.
`'reduction_script'` and `'arguments'` are added by the `data_ready` function in queue_processor.py.
`'reduction_data'` is added by the `reduction_complete` function in the queue_processor.py.
`'message'` will usually be empty unless an error has been caught and passed back.


### Selecting run variables

Run variables (for initial runs that come off the instrument) are selected in the `create_variables_for_run` utils method. Appropriate variables are chosen in the following order:
* First, check if there are instrument variables for the associated experiment reference number.
* If not, check for instrument variables set with a `start_run` before the associated run number; if there are any, choose the most recent set.
* If no variables are found, default variables are created from the reduction script and those are used.

### Upcoming InstrumentVariables

Upcoming InstrumentVariables are fetched in two ways.

The first is by run number. Any instrument variables with a start run larger than the last processed run number for that instrument are returned.

The second is by experiment reference number. This checks with ICAT for any experiments on that instrument where the end date is in the future. These are then used to return all instrument variables with a matching reference number. It is possible that this may not return all that is expected as the experiments may not have been loaded into ICAT yet.

### Script Preview

The reduction script and variables are combined in a preview to make a single, runnable script, in `preview_script()` in `reduction_variables/utils.py`. To do this, any imports of `reduce_vars` is removed, and a class declaration with the imported name substituted. This class declaration contains declarations of `standard_vars` and `advanced_vars`, generated from the relevant reduction variables. The result is reasonably robust to arbitrary changes in the script, since the semantics of import statements are fairly limited, and the variable definitions are fabricated entirely, rather than run as substitutions on existing code.


### Base64 Images

When a reduction job output some .png files the `reduction_complete` method of the queue_processor will read these and convert them to base64 encoded text to be stored in the database. The following code achieves this:

```python
graphs = glob.glob(location + '*.[pP][nN][gG]')
for graph in graphs:
    with open(graph, "rb") as image_file:
        encoded_string = 'data:image/png;base64,' + base64.b64encode(image_file.read())
        if reduction_run.graph is None:
            reduction_run.graph = [encoded_string]
        else:
            reduction_run.graph.append(encoded_string)
```
`glob.glob` will search for any file ending in .png (case-insensitive) and return their paths as a list. Each file is then iterated over, read in and encoded to base64. `'data:image/png;base64,'` is prepended to the encoded string as this is required to tell the browser what to expect in the encoded text.

When it comes to displaying these in the browser all major browsers can handle the encoded text in the `src` attribute of an `<img>` tag.

Internet Explorer doesn't have support for Data URI navigation (loading a page via an encoded string) so this makes opening the image in a new tab difficult. To resolve this there is a `fixIeDataURILinks` function in `base.js` that will take any `<a>` tags that have a `href` attribute starting with `data:image/jpeg;base64` and set an onclick handler that instead of opening the encoded string as a new tab it creates a new popup window and sets the body of the popup as the image.

```javascript
var fixIeDataURILinks = function fixIeDataURILinks(){
    $("a[href]").each(function(){
        if($(this).attr('href').indexOf('data:image/jpeg;base64') === 0){
            var output = this.innerHTML;    // This returns the '<img>' tag with the encoded string
            $(this).on('click', function openDataURIImage(event){
                event.preventDefault();
                var win = window.open("about:blank");
                win.document.body.innerHTML = output;
                win.document.title = document.title;
            });
        }
    });
};
```

### Error pages

There are 4 HTTP error pages supplied in the application. These handle [400](http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.1), [403](http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.4), [404](http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.5) and [500](http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.5.1) HTTP error codes, each having a corresponding template file.

The logic for these can be found in `views.py` of the autoreduce_webapp application and included in `urls.py` as the following:
```python
handler400 = 'autoreduce_webapp.views.handler400'
handler403 = 'autoreduce_webapp.views.handler403'
handler404 = 'autoreduce_webapp.views.handler404'
handler500 = 'autoreduce_webapp.views.handler500'
```

If the `admin_email` setting has been set in the database this will be shown to the user for additional help.

### Notifications

The system provides a mechanism to display messages to the users using notifications at the top of pages. These notification can have varying severity (info, warning or error) and there is the option to display to all users or only staff members (instrument scientists). Notifications can be manually added by admins of the system using the built in django admin database portal. It is possible from within here to create, delete and modify notifications as well as activate/deactivate.

Some notifications are displayed automatically, such as when there is a failed reduction job, and these are not stored in the database as they are dependant on the displayed data.

### Log Files

The WebApp saves all log messages to `[WebAppRoot]/autoreduction.log`.

The autoreduction service saves all log messages to `/var/log/autoreduction.log`.

Note: Currently these logs aren't rotated so watch file sizes!


## Possible Problems & Solutions

### Queue processor unable to connect to ActiveMQ

First check that the details in `settings.py` are correct and that the broker is set as a list of tuples. (E.g. `'broker' : [("queue.example.com", 61613)]`)

If these details look correct, next check if ActiveMQ is using SSL or not. If it is, make sure the `use_ssl` property of the queue_processor client is set to True, otherise ensure it is set to False.

To set ActiveMQ to use SSL edit the activemq.xml with something similar to:
```xml
<transportConnectors>
    <transportConnector name="stomp+ssl" uri="stomp+ssl://0.0.0.0:61613?maximumConnections=1000&amp;wireFormat.maxFrameSize=104857600"/>
</transportConnectors>
```
### Import Errors in reduction script

As the reduction script will be loaded on both the web server and autoreduction server (to access the variables) it is possible that an ImportError exception is thrown.
An error in the log will be recorded with the missing module and a notification should be created with the same message. 

To resolve this you will need to either modify the reduction script not to use the module or install the missing module on both servers (and make sure it is added to the appropriate system path).

### AttributeError: 'module' object has no attribute 'standard_vars'

This indicates that the `reduce.py` script doesn't contain a `standard_vars` variable. The most likely cause of this is either the `reduce.py` doesn't import `reduce_vars.py` or the `reduce.py` imports the variables as a different name. E.g. `from reduce_vars import * as rv`

### MySQL server has gone away

This happens when the connection to MySQL has been idle for longer than the wait period (default 8 hours). A fix should now be included but if it presents itself again restarting the 'AutoreduceQueueProcessor" service should resolve the issue.

See: https://code.djangoproject.com/ticket/21597#comment:29 

### Mantid unicode errors
The mantid program does not work well with unicode format, so any file path names passed to the scripts need to be in Ascii. 
