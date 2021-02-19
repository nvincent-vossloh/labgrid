# pylint: disable=no-member
import subprocess
import re
import attr

from ..factory import target_factory
from ..step import step
from .common import Driver
from .exception import ExecutionError
from ..util.helper import processwrapper
from ..util.managedfile import ManagedFile


@target_factory.reg_driver
@attr.s(eq=False)
class QuartusHPSDriver(Driver):
    bindings = {
        "interface": {"AlteraUSBBlaster", "NetworkAlteraUSBBlaster"},
    }

    image = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str))
    )

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        # FIXME make sure we always have an environment or config
        if self.target.env:
            self.tool = self.target.env.config.get_tool('quartus_hps') or 'quartus_hps'
            self.jtag_tool = self.target.env.config.get_tool('jtagconfig') or 'jtagconfig'
        else:
            self.tool = 'quartus_hps'
            self.jtag_tool = 'jtagconfig'

    def _get_cable_number(self):
        """
        Returns the JTAG cable number with an intact JTAG chain for the USB path of the device.
        """
        cmd = self.interface.command_prefix + [self.jtag_tool]
        jtagconfig_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE
        )
        stdout, _ = jtagconfig_process.communicate()

        regex = rf".*(\d+)\) .* \[{re.escape(self.interface.path)}]\n(.*)\n"
        jtag_mapping = re.search(regex, stdout.decode("utf-8"), re.MULTILINE)
        if jtag_mapping is None:
            raise ExecutionError("Could not get cable number for USB path {}"
                                 .format(self.interface.path))

        cable_number, first_chain = jtag_mapping.groups()
        if "JTAG chain broken" in first_chain:
            raise ExecutionError(first_chain.strip())

        return int(cable_number)

    @Driver.check_active
    @step(args=['filename', 'address'])
    def flash(self, filename=None, address=0x0):
        if filename is None and self.image is not None:
            filename = self.target.env.config.get_image_path(self.image)
        mf = ManagedFile(filename, self.interface)
        mf.sync_to_resource()

        assert isinstance(address, int)

        cable_number = self._get_cable_number()
        cmd = self.interface.command_prefix + [self.tool]
        cmd += [
            "--cable={}".format(cable_number),
            "--addr=0x{:X}".format(address),
            "--operation=P {}".format(mf.get_remote_path()),
        ]
        processwrapper.check_output(cmd)

    @Driver.check_active
    @step(args=['address', 'size'])
    def erase(self, address=None, size=None):

        cable_number = self._get_cable_number()
        cmd = self.interface.command_prefix + [self.tool]
        cmd += [
            "--cable={}".format(cable_number),
            "--operation=E",
        ]
        if address:
            cmd += ["--addr=0x{:X}".format(address)]
        if size:
            cmd += ["--size=0x{:X}".format(size)]
        processwrapper.check_output(cmd)
