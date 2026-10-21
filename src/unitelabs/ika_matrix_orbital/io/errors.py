class DeviceUnreachable(Exception):
    """The serial connection to the thermoshaker could not be opened. Check the port name, the USB cable and that no other program holds the port."""  # noqa: E501


class NoResponse(Exception):
    """The thermoshaker did not answer within the timeout. Check the cable and the serial parameters, then retry."""


class UnexpectedResponse(Exception):
    """The thermoshaker answered, but the reply could not be interpreted. The raw reply is included in the message."""


class NotConnected(Exception):
    """No transport is open. The connector opens the device at start-up, so this indicates a lost connection."""
