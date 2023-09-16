WaveHat
=======

Thin wrapper for interacting with [Waveshare's SIM868](https://www.waveshare.com/product/raspberry-pi/hats/iot/gsm-gprs-gnss-hat.htm) Raspberry Pi hat.


Installation
------------

Clone this repository to a temporary directory using [GIT](https://git-scm.com/) (or alternatively
download as [.zip](https://github.com/lliendo/WaveHat/archive/master.zip)) by running:

```bash
git clone https://github.com/lliendo/WaveHat.git
cd WaveHat
python setup.py install
```

WaveHat relies on the `RPi.GPIO` and `pyserial` modules.

I highly recommend you to use a Python virtual environment to avoid polluting the
system-wide's Python installation (at least if you intend to try the module).


Features
--------

This Python module provides the following features to easily use the hat:

* Works regardless AT echo is on/off.
* Turn on/off the hat. (it takes 4 seconds to do this).
  The class automatically turns it on if is off when creating the object.
* Turn on/off the GNSS.
* Get GNSS position (it might take few seconds to get an initial reading).
* Send a SMS. If the message is too long it is automatically splitted and
  each part sent.
* Read all/nth SMS from a source.
* Delete all/nth SMS from a source.
* Automatically decode response strings if an encoding is provided.
* Send arbitrary commands to the device.

The source code is intended to be as synthetic and readable as possible
so it can be extended or modified for specific needs with little effort.


Documentation
-------------

This documentation assumes that you have already enabled the Raspberry Pi's UART
from `/boot/config.txt`. If you haven't done it yet, edit `/boot/config.txt` and add:

```bash
# Enable UART.
enable_uart=1
```

You need to restart the board for this to take effect.

Before installing and using the module please identify the correct device
file under `/dev` that maps to the hat.

In my Raspberry Pi 3 this is `/dev/ttyAMA0`. Check that the hat is currently on
(or manually turn it on by physically pressing the PWRKEY for about 4 seconds) and
launch a program to actually test that is operational. You can do this with many different
programs, I've personally used `microcom` which is directly available from Raspberry Pi OS.
To install it run (as root):

```bash
apt-get install microcom
```

Then run:

```bash
microcom -p /dev/X -s 115200  # Where X is your hat mapped device filename.
```

type in the `AT` command and press enter. You should see something like this:

```bash
connected to /dev/ttyAMA0
Escape character: Ctrl-\
Type the escape character to get to the prompt.
AT
OK
```

At this point the hat seems to be responding correctly so you should be able to
use the Python module without issues.

Note that the test performed before was done as the **root** user.

You could find permission issues if a non root user attempts to open files under the `/dev` directory.
You can fix this by adding a non privileged user to the `tty`, `dialout` and `gpio`
groups. For example my `/etc/group` file shows:

```bash
tty:x:5:lucas
dialout:x:20:pi,lucas
gpio:x:997:pi,lucas
```

indicating that the `lucas` username is a member of those groups. Check the relevant
user administration man pages in order to do this. Retry the above steps with
a regular user to verify that you don't get any permission errors.

Now the coding part. Here's is an example that shows almost all the `SIM868` class API:

```python
from pprint import pprint
from wavehat import SIM868


def main():
    # Check on which `/dev` file the hat is. On my Raspberry Pi is `/dev/ttyAMA0`.
    sim868 = SIM868(device='/dev/ttyAMA0', encoding='latin-1')

    # Get a list of all SMSes.
    pprint(sim868.get_smses())

    # Try to get the first SMS from the default source (SM, which is the simcard).
    pprint(sim868.get_sms(1))

    # Uncomment to try to delete the 1st. SMS from default source (if exists).
    # pprint(sim868.delete_sms(1))

    # Uncomment to delete all SMSes from default source.
    # pprint(sim868.delete_smses())

    # Turn on the GNSS and attempt to get the current position but should
    # not report it immediately as it takes time to acquire signal, so you might
    # need to call `sim868.position` after some time (30 seconds should be enough).
    sim868.turn_gnss()
    pprint(sim868.position)

    # Try to send a SMS to given number.
    mobile_number = ''  # Complete test mobile number! (E.g: +54...)
    sim868.send_sms('Hello from SIM868 hat!', mobile_number)

    # Turn GNSS off.
    # sim868.turn_gnss(on=False)

    # Turn hat off.
    # sim868.turn_hat(on=False)

if __name__ == '__main__':
    main()
```

To directly send commands to the device there are two ways:

```python
from wavehat import SIM868

sim868 = SIM868(device='/dev/ttyAMA0', encoding='latin-1')
sim868.at('CGNSINF')
```

This will translate internally to `AT+CGNSINF\r`. As you can see the `AT+` prefix
and the `\r` suffix are added automatically. This is because there are many AT commands
that follow this format. Nevertheless if you need to send a command that does not follow
this format you can do:

```python
from wavehat import SIM868

sim868 = SIM868(device='/dev/ttyAMA0', encoding='latin-1')
sim868.at('ATE0\r', raw=True)  # Turn AT echo off.
```

When the `at` method receives the `raw` keyword argument with a `True` value it expects
the command to be entirely specified by the user, effectively cancelling the prefix and
suffix mentioned before. Make sure to add a trailing `\r` to each command you send or
the device will keep expecting more bytes as part of that command!

Note that these calls will return a raw response from the device. There's another method
in the class that returns a pre-processed output that is easier to work with:

```python
from wavehat import SIM868

sim868 = SIM868(device='/dev/ttyAMA0', encoding='latin-1')
at_response, status = sim868.split_at_response(sim868.at('CGNSINF'))
```

The `split_at_response` method returns a tuple with a list containing all the
parts from the AT response splitted accordingly as the first component and a status
as the last component. You can use the status to verify if the command was successful
or not.

By default long SMSes are split into chunks of 160 characters. If you need
to use a different limit you can call `send_sms` with the `sms_max_length=N`
keyword argument to override it.

Upon any errors a `SIM868Error` exception is raised.

If you still need to do something that is currently not supported by the module
I encourage you to take a look at the source code and hack it as it has been
designed to be easily understood.


Tested devices
--------------

* Raspberry Pi 3 Model B V1.2


Licence
-------

WaveHat is distributed under the [GNU LGPLv3](https://www.gnu.org/licenses/lgpl.txt) license.


Authors
-------

* Lucas Liendo.
