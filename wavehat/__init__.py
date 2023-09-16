"""
This file is part of WaveHat.

WaveHat is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

WaveHat is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
Lesser GNU General Public License for more details.

You should have received a copy of the Lesser GNU General Public License
along with WaveHat. If not, see <http://www.gnu.org/licenses/>.

Copyleft 2023 - present, Lucas Liendo.
"""

import RPi.GPIO as GPIO
import math
import os
import serial
import time


class SIM868Error(Exception):
    pass


class SIM868:
    """
    Thin wrapper for interacting with Waveshare's SIM868 Raspberry Pi hat.

    :param device: Absolute path to the serial device. Default path: '/dev/ttyS0'.
    :param baud_rate: The baud rate for the serial device. Default baud rate: 115200.
    :param encoding: An encoding to be used each time a command is sent or
        received from the serial device. Default: None.
    """

    AT_END_MARK = b'\r\n'
    AT_ERROR = b'ERROR\r\n'
    AT_OK = b'OK\r\n'
    AT_PROMPT = b'> '
    DEFAULT_POWER_ON_TIME = 4  # In seconds.
    DEFAULT_SMS_SOURCE = 'SM'
    GNSS_FIELDS = [
        'gnss_run_status', 'fix_status', 'utc_datetime', 'latitude', 'longitude',
        'msl_altitude', 'speed_over_ground', 'course_over_ground', 'fix_mode',
        'reserved1', 'hdop', 'pdop', 'vdop', 'reserved2', 'gnss_satellites_in_view',
        'gnss_satellites_used', 'glonass_satellites_used', 'reserved3', 'c/n0_max',
        'hpa', 'vpa',
    ]
    OUTPUT_PIN = 7  # GPIO pin used for turning on/off the hat.
    SMS_MAX_LENGTH = 160
    SMS_FIELDS = ['source', 'from', 'date', 'sms']
    READ_TIMEOUT = 1

    def __init__(self, device='/dev/ttyS0', baud_rate=115200, encoding=None):
        self._encoding = encoding
        self._serial_line = serial.Serial(
            port=device, baudrate=baud_rate, timeout=self.READ_TIMEOUT
        )
        self.hat_powered = self._is_hat_powered()
        self.turn_hat()
        self.at_echo = 'AT' in self.at('AT')  # Check if AT echo is on or off.

    def _is_hat_powered(self):
        """
        Check if the serial device exists and is turned on.

        :return: A boolean indicating if the hat is powered on or off.
        """
        self._serial_line.flush()
        self._serial_line.write(b'AT\r')
        at_expected_responses = [
            b'AT\r\r\nOK\r\n',  # AT echo is on.
            b'\r\nOK\r\n',  # AT is off.
        ]
        at_response = self._serial_line.read(size=len(at_expected_responses[0]))
        hat_powered = False

        if at_response in at_expected_responses:
            hat_powered = True
            self._serial_line.timeout = 0  # Clear the initial timeout.

        return hat_powered

    def _is_at_response_complete(self, at_response):
        """
        Tell if a response from the device is complete.

        :param at_response: A bytesarray containing the response from the device.
        :return: A boolean indicating if the AT response is complete or not.
        """
        return at_response.endswith(self.AT_OK) or \
            at_response.endswith(self.AT_ERROR) or \
            at_response.endswith(self.AT_PROMPT)

    def _press_power_key(self):
        """
        Send a `GPIO.LOW` signal for `DEFAULT_POWER_ON_TIME` seconds
        to turn on or off the hat.
        """
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.OUTPUT_PIN, GPIO.OUT)
        GPIO.output(self.OUTPUT_PIN, GPIO.LOW)
        time.sleep(self.DEFAULT_POWER_ON_TIME)
        GPIO.output(self.OUTPUT_PIN, GPIO.HIGH)
        GPIO.cleanup()

    def _encode_or_decode(self, string, encode=True):
        encode_decode = getattr(string, f"{'encode' if encode else 'decode'}")
        return encode_decode(self._encoding) if self._encoding else string

    def _format_command(self, command, raw):
        formatted_command = (
            f"{f'{command}' if raw else f'AT+{command}'}" + ('' if raw else '\r')
        )

        return self._encode_or_decode(formatted_command)

    def split_at_response(self, at_response):
        """
        Split a response into uselful tokens and get the status.

        :param at_response: A raw response from the device.
        :return: A tuple containing a list of tokens and a status.
        """
        tokens = [
            token for token in at_response.split(self.AT_END_MARK.decode('ascii')) if token
        ]
        status = tokens.pop(len(tokens) - 1)

        # Return relevant tokens regardless AT echo is on or off.
        return tokens[1 if self.at_echo else 0:], status

    def at(self, command, raw=False):
        """
        Send an AT command to Waveshare's hat.

        :param command: A string containing the AT command without
            the `AT+` prefix nor the `\r` ending. E.g: `.at('CGNSINF')`.
        :param raw: Allows to send a full AT command when this
            kwarg is `True`. E.g: `.at('AT+CGNSINF\r')`.
        :return: Either an encoded string if this object was supplied the
            `encoding` kwarg or a `bytearray` containing the raw response
            from the device.
        """
        if not self.hat_powered:
            raise SIM868Error("Error - The device is not turned on.")

        formatted_command = self._format_command(command, raw)
        self._serial_line.write(formatted_command)
        at_response = b''

        while not self._is_at_response_complete(at_response):
            if self._serial_line.in_waiting > 0:
                at_response += self._serial_line.read()

        self._serial_line.flush()

        return self._encode_or_decode(at_response, encode=False)

    def turn_hat(self, on=True):
        """
        Turn on/off Waveshare's hat.

        :param on: Boolean indicating if the hat should be turned on or off.
        """
        if on and not self.hat_powered:
            self._press_power_key()
            self.hat_powered = True
            self._serial_line.flush()
            self._serial_line.reset_input_buffer()

        if not on and self.hat_powered:
            self._press_power_key()
            self.hat_powered = False

    def turn_gnss(self, on=True):
        """
        Turn on/off the GNSS.

        :param on: Boolean indicating if the GNSS should be turned on or off.
        """
        return self.at(f'CGNSPWR={1 if on else 0}')

    def _check_at_status_response(self, at_response, status, error_message):
        if status == self.AT_ERROR.decode('ascii').strip():
            raise SIM868Error(f'Error - {error_message}. Details: {at_response}.')

    @property
    def position(self):
        """
        Get a GNSS reading.

        You might need to wait few seconds after powering the GNSS before
        calling this propery to get a valid reading as signal reception
        is not immediate.

        :return: A dictionary containing all the fields specified in the
            `SIM868.GNSS_FIELDS` class attribute list.
        """
        at_response, status = self.split_at_response(self.at('CGNSINF'))
        self._check_at_status_response(
            at_response, status, 'CGNSINF failed. Unable to get GNSS reading'
        )
        gnss_values = at_response[0].replace('+CGNSINF: ', '').split(',')
        position = {}

        for gnss_field, gnss_value in zip(self.GNSS_FIELDS, gnss_values):
            if gnss_value:
                try:
                    position[gnss_field] = int(gnss_value)
                except ValueError:
                    position[gnss_field] = float(gnss_value)
            else:
                position[gnss_field] = None

        return position

    def _valid_sms(self, nth):
        """
        Check if the nth SMS is within the valid range of available SMSes.

        SMSes start at index 1 (not zero).

        :param nth: The SMS number to be checked.
        :return: A Boolean value.
        """
        _, max_capacity = self.total_smses()
        return (1 <= nth <= max_capacity)

    def total_smses(self, source=DEFAULT_SMS_SOURCE):
        """
        Tell the number of current SMSes and max capacity from source.

        :param source: The source where to retrieve the SMSes count.
            Default value: "SM" which is the simcard.
        :return: A tuple with two integers indicating the total used
            SMSes slots and maximum capacity.
        """
        at_response, status = self.split_at_response(self.at(f'CPMS="{source.upper()}"'))
        self._check_at_status_response(
            at_response, status,
            f'CPMS failed. Unable to get total number of SMSes from {source}'
        )
        message_storage = at_response[0].replace('+CPMS: ', '')
        total, max_capacity, *_ = [
            int(n) for n in message_storage.split(',')
        ]

        return total, max_capacity

    def get_sms(self, nth, source=DEFAULT_SMS_SOURCE, check_nth=True):
        """
        Get the nth SMS from source.

        :param nth: The SMS number to be retrieved. This number must
            be between 1 and the total SMSes received.
        :param source: The source where to retrieve the SMS.
            Default value: `DEFAULT_SMS_SOURCE` which is the simcard.
        :param check_nth: If True it will raise an error if the SMS number
            is not in the expected range.
        :return: A dictionary containing all the fields specified in the
            `SIM868.SMS_FIELDS` class attribute list. The `nth` key is also
            added to record the index.
        """
        if check_nth and (not self._valid_sms(nth)):
            raise SIM868Error(f'Error - Message #{nth} is out of range.')

        self.at('CMGF=1')
        self.at(f'CPMS="{source.upper()}"')
        at_response, status = self.split_at_response(self.at(f'CMGR={nth}'))
        self._check_at_status_response(
            at_response, status,
            f'CMGS failed. Unable to read SMS #{nth} from {source.upper()}'
        )
        sms = None

        if at_response:
            sms_metadata = at_response[0].replace('+CMGR: ', '').split('","')
            sms_metadata.pop(2)  # This field seems to be always empty so skip it.
            sms = {
                key: value.strip('"')
                for key, value in zip(self.SMS_FIELDS, sms_metadata + [at_response[1]])
            }
            sms['nth'] = nth

        return sms

    def get_smses(self, source=DEFAULT_SMS_SOURCE):
        """
        Get all SMSes from source.

        :param source: The source where to retrieve SMSes. Default value: "SM"
            which is the simcard.
        :return: A list of dictionaries containing all the available SMSes.
            Each dictionary contains the following keys: 'source',
            'from', 'number', 'date', 'sms'.
        """
        total_smses, _ = self.total_smses()
        smses, nth = [], 1

        while total_smses > 0:
            if (nth_sms := self.get_sms(nth, source=source, check_nth=False)):
                smses.append(nth_sms)
                total_smses -= 1

            nth += 1

        return smses

    def delete_sms(self, nth, source=DEFAULT_SMS_SOURCE, check_nth=True):
        """
        Delete the nth SMS from source.

        Note that SMSes don't get their indices re-arranged after deletion.

        :param nth: The SMS number to be deleted. This number must
            be between 1 and the total current SMSes received.
        :param source: The source where to delete the SMS.
            Default value: `DEFAULT_SMS_SOURCE` which is the simcard.
        :param check_nth: If `True` it will raise an error if the SMS number
            is not in the expected range. Default: True.
        :return: The deleted SMS.
        """
        if sms := self.get_sms(nth, source=source, check_nth=check_nth):
            self.at(f'CPMS="{source.upper()}"')
            at_response, status = self.split_at_response(self.at(f'CMGD={nth}'))
            self._check_at_status_response(
                at_response, status,
                f'CMGD failed. Unable to delete SMS #{nth} from {source.upper()}'
            )

        return sms

    def delete_smses(self, source=DEFAULT_SMS_SOURCE):
        """
        Delete all SMS from source.

        :param source: Where to delete the SMS from.
        :return: A list of all deleted SMSes.
        """
        smses = self.get_smses(source=source)

        for sms in smses:
            self.delete_sms(sms['nth'], source=source, check_nth=False)

        return smses

    def _send_sms(self, sms_part, mobile_number):
        """
        Send a SMS.

        :param sms_part: A string containing the SMS or part of it.
        :param mobile_number: A string containing the receiver of the SMS.
            E.g: +923234206521.
        """
        self.at('CMGF=1')
        at_response = self.at(f'CMGS="{mobile_number}"')

        if not at_response.endswith(self.AT_PROMPT.decode('ascii')):
            self._serial_line.flush()
            raise SIM868Error('Error - Unable to get AT prompt to push SMS to device.')

        # The \x1A byte makes the '> ' prompt end and the SMS to be sent.
        at_response, status = self.split_at_response(
            self.at(f'{sms_part}\x1A', raw=True)
        )
        self._check_at_status_response(
            at_response, status, 'CMGS failed. Unable to send SMS'
        )

        return at_response, status

    def send_sms(self, message, mobile_number, sms_max_length=SMS_MAX_LENGTH):
        """
        Send a SMS (and split it if necessary).

        This method is a wrapper for `_send_sms` which actually sends the SMS.

        :param message: A string containing the SMS. If the messsage is longer than
            `max_length` it will be splitted and each chunk sent in a separate
            SMS.
        :param mobile_number: A string containing the receiver of the SMS.
            E.g: +923338206521.
        """
        if not message or not mobile_number:
            raise SIM868Error(f"Error - `message` and/or `mobile_number` can't be empty.")

        total_offsets = math.ceil(len(message) / self.SMS_MAX_LENGTH)
        sms_parts = [
            message[offset * sms_max_length : (offset + 1) * sms_max_length]
            for offset in range(0, total_offsets)
        ]
        at_responses = []

        for sms_part in sms_parts:
            at_responses.append(self._send_sms(sms_part, mobile_number))

        return at_responses
