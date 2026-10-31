import ctypes
import time

# Keep the system awake while the print stack runs (the Windows equivalent
# of the Mac app's `caffeinate -dis`): ES_CONTINUOUS | ES_SYSTEM_REQUIRED.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def main():
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        pass
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)


if __name__ == "__main__":
    main()
