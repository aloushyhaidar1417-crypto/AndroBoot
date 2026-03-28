import os
import subprocess
import shutil
import time
import ctypes

class EmulatorManager:
    def __init__(self):
        self.process = None
        self.embedded_dir = os.path.join(os.getcwd(), "core", "engine")

    def check_engine(self):
        """Check for Windows Hypervisor Platform via Win32 API."""
        try:
            # Load the library
            whp_lib = ctypes.WinDLL("WinHvPlatform.dll")
            
            # Define types for WHvGetCapability
            capability = ctypes.c_uint64(0)
            return_size = ctypes.c_uint32(0)
            
            # WHvCapabilityCodeHypervisorPresent = 0x00000000
            # We call WHvGetCapability to see if the hypervisor is actually active.
            result = whp_lib.WHvGetCapability(
                0, 
                ctypes.byref(capability), 
                ctypes.sizeof(capability), 
                ctypes.byref(return_size)
            )
            
            return result == 0 and capability.value != 0
        except:
            return False

    def check_haxm(self):
        """Check if Intel HAXM is available as an alternative accelerator."""
        try:
            subprocess.check_output("sc query intelhaxm", shell=True, stderr=subprocess.STDOUT)
            return True
        except:
            return False

    def _resolve_bin(self, name):
        """Helper to find the absolute path of a QEMU binary."""
        # Prioritize the internal Embedded Engine folder
        embedded_path = os.path.join(self.embedded_dir, f"{name}.exe" if os.name == 'nt' else name)
        if os.path.exists(embedded_path):
            return embedded_path

        path = shutil.which(name)
        if not path and os.name == 'nt':
            # Check default Windows installation path
            fallback = os.path.join("C:\\Program Files\\qemu", f"{name}.exe")
            if os.path.exists(fallback):
                return fallback
        return path if path else name

    def _resolve_ovmf(self):
        """Helper to find the OVMF firmware for UEFI boot."""
        paths = [
            os.path.join(os.getcwd(), "OVMF.fd"),
            os.path.join(os.getcwd(), "core", "OVMF.fd"),
            os.path.join("C:\\Program Files\\qemu", "OVMF.fd"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return None

    def get_system_ram(self):
        """Returns total system RAM in MB using Win32 API."""
        if os.name == 'nt':
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys / (1024 * 1024))
        return 4096

    def check_utm(self):
        """Check if UTM (utmctl) is installed."""
        return self._resolve_bin("utmctl") != "utmctl"

    def check_qemu(self):
        """Keep fallback check for QEMU."""
        return self._resolve_bin("qemu-system-x86_64") != "qemu-system-x86_64"

    def check_vbox(self):
        """Check if VirtualBox (VBoxManage) is installed."""
        return self._resolve_bin("VBoxManage") != "VBoxManage"

    def check_vmware(self):
        """Check if VMware (vmrun) is installed."""
        return self._resolve_bin("vmrun") != "vmrun"

    def enable_engine(self):
        """Attempts to enable the necessary Windows features for hardware acceleration."""
        # HypervisorPlatform is the key feature for QEMU's WHPX accelerator.
        # VirtualMachinePlatform is recommended for modern virtualization compatibility.
        features = ["HypervisorPlatform", "VirtualMachinePlatform", "Microsoft-Hyper-V-All"]
        ps_script = "; ".join([f"Enable-WindowsOptionalFeature -Online -FeatureName {f} -All" for f in features])
        cmd = ["powershell.exe", "Start-Process", "powershell.exe", "-ArgumentList", 
               f"'{ps_script}'", "-Verb", "RunAs"]
        return subprocess.Popen(cmd)

    def create_disk(self, disk_path, size_gb):
        if not os.path.exists(disk_path):
            os.makedirs(os.path.dirname(disk_path), exist_ok=True)
            exe = self._resolve_bin("qemu-img")
            cmd = [exe, "create", "-f", "qcow2", disk_path, f"{size_gb}G"]
            subprocess.run(cmd, capture_output=True)

    def launch(self, iso_path, disk_path, ram, cores, resolution="1280x720", desktop_mode=False, use_uefi=True, force_tcg=False):
        """Smart Launch: Uses UTM if available, falls back to QEMU."""
        if self.check_utm() and not force_tcg:
            utm_bin = self._resolve_bin("utmctl")
            vm_name = os.path.basename(iso_path).replace(".iso", "")
            cmd = [utm_bin, "start", vm_name]
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return self.process

        # Fallback to QEMU
        if self.check_qemu():
            qemu_exe = self._resolve_bin("qemu-system-x86_64")
            is_whpx = self.check_engine() if not force_tcg else False
            accel = "whpx" if is_whpx else "tcg"
            
            # Use host CPU with Hyper-V enlightenments for better stability on Windows hosts
            if is_whpx:
                # Disabling 'monitor' prevents WHPX from crashing when the guest executes MONITOR/MWAIT (Exit Code 4)
                cpu_type = "host,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time,hv_synic,hv_stimer,+x2apic,-monitor"
            else:
                # Android 9+ requires SSE4.2/SSSE3; 'max' is best for Software Emulation (TCG)
                cpu_type = "max"
            
            cmd = [
                qemu_exe,
                "-machine", "type=q35",
                "-m", str(ram),
                "-smp", str(cores),
                "-drive", f"file={disk_path},format=qcow2,if=virtio",
                "-cdrom", iso_path,
                "-boot", "order=d,once=d,menu=on",
                "-vga", "virtio",
                "-display", "sdl",
            ]

            if is_whpx:
                cmd.extend(["-accel", "whpx,kernel-irqchip=off"])
            
            # Enable multi-threaded TCG for better software emulation speed
            cmd.extend(["-accel", "tcg,thread=multi", "-cpu", cpu_type])
            
            if use_uefi:
                ovmf = self._resolve_ovmf()
                if ovmf: cmd.extend(["-bios", ovmf])
            if desktop_mode:
                cmd.extend(["-device", "virtio-tablet-pci", "-device", "virtio-keyboard-pci"])

            self.process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
            return self.process
        
        return None

    def launch_vbox(self, iso_path, ram, cores):
        """Launch using VirtualBox (VBoxManage) as a fallback."""
        vbox = self._resolve_bin("VBoxManage")
        vm_name = "AndroidLoader_Fallback_VM"
        
        try:
            # Cleanup existing VM if it exists
            subprocess.run([vbox, "unregistervm", vm_name, "--delete"], capture_output=True)
            
            # Create and Register VM
            subprocess.run([vbox, "createvm", "--name", vm_name, "--register"], check=True)
            
            # Set Hardware
            subprocess.run([vbox, "modifyvm", vm_name, 
                          "--memory", str(ram), 
                          "--cpus", str(cores), 
                          "--ostype", "Linux_64", 
                          "--graphicscontroller", "vmsvga",
                          "--vram", "128"], check=True)
            
            # Attach ISO
            subprocess.run([vbox, "storagectl", vm_name, "--name", "IDE", "--add", "ide"], check=True)
            subprocess.run([vbox, "storageattach", vm_name, "--storagectl", "IDE", 
                          "--port", "0", "--device", "0", "--type", "dvddrive", "--medium", iso_path], check=True)
            
            # Start
            self.process = subprocess.Popen([vbox, "startvm", vm_name, "--type", "gui"])
            return self.process
        except Exception as e:
            raise Exception(f"VirtualBox Error: {str(e)}")

    def launch_vmware(self, iso_path, ram, cores):
        """Launch using VMware (vmrun) as a high-performance fallback."""
        vmrun = self._resolve_bin("vmrun")
        vm_dir = os.path.join(os.getcwd(), "disks", "VMware_Fallback")
        os.makedirs(vm_dir, exist_ok=True)
        vmx_path = os.path.join(vm_dir, "android.vmx")
        
        # Generate a standard VMX configuration file
        vmx_content = f"""
.encoding = "UTF-8"
config.version = "8"
virtualHW.version = "12"
memsize = "{ram}"
numvcpus = "{cores}"
guestOS = "otherlinux-64"
ide1:0.present = "TRUE"
ide1:0.deviceType = "cdrom-image"
ide1:0.fileName = "{os.path.abspath(iso_path)}"
ethernet0.present = "TRUE"
ethernet0.connectionType = "nat"
usb.present = "TRUE"
ehci.present = "TRUE"
pciBridge0.present = "TRUE"
pciBridge4.present = "TRUE"
pciBridge4.virtualDev = "pcieRootPort"
pciBridge4.functions = "8"
vmci0.present = "TRUE"
hpet0.present = "TRUE"
displayName = "Android OS Loader - VMware"
"""
        try:
            with open(vmx_path, "w") as f:
                f.write(vmx_content)
            
            # Start the VM in the VMware GUI
            self.process = subprocess.Popen([vmrun, "-T", "ws", "start", vmx_path, "gui"])
            return self.process
        except Exception as e:
            raise Exception(f"VMware Error: {str(e)}")

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process = None
