#!/usr/bin/env python3
"""
Audio Device Diagnostics
Lists all available audio devices and tests basic functionality
"""

import sounddevice as sd
import sys

def list_devices():
    """List all audio devices with details"""
    print("=" * 80)
    print("AUDIO DEVICES")
    print("=" * 80)
    
    devices = sd.query_devices()
    
    print(f"\nTotal devices found: {len(devices)}")
    print(f"Default input device: {sd.default.device[0]}")
    print(f"Default output device: {sd.default.device[1]}")
    
    print("\n" + "-" * 80)
    print("INPUT DEVICES (for recording):")
    print("-" * 80)
    
    for i, device in enumerate(devices):
        if device['max_input_channels'] >= 2:
            print(f"\nDevice {i}: {device['name']}")
            print(f"  Max Input Channels: {device['max_input_channels']}")
            print(f"  Default Sample Rate: {device['default_samplerate']}")
            print(f"  Host API: {sd.query_hostapis(device['hostapi'])['name']}")
            
            # Highlight Traktor
            if 'traktor' in device['name'].lower():
                print("  >>> THIS IS A TRAKTOR DEVICE <<<")
    
    print("\n" + "-" * 80)
    print("OUTPUT DEVICES (for monitoring):")
    print("-" * 80)
    
    for i, device in enumerate(devices):
        if device['max_output_channels'] >= 2:
            print(f"\nDevice {i}: {device['name']}")
            print(f"  Max Output Channels: {device['max_output_channels']}")
            print(f"  Default Sample Rate: {device['default_samplerate']}")
            print(f"  Host API: {sd.query_hostapis(device['hostapi'])['name']}")
            
            # Highlight Traktor
            if 'traktor' in device['name'].lower():
                print("  >>> THIS IS A TRAKTOR DEVICE <<<")
    
    print("\n" + "=" * 80)

def test_device(device_index):
    """Test if a device can be opened"""
    print(f"\nTesting device {device_index}...")
    
    try:
        device = sd.query_devices(device_index)
        print(f"Device: {device['name']}")
        
        # Try to open input stream
        if device['max_input_channels'] >= 2:
            print("Testing INPUT stream...")
            stream = sd.InputStream(
                device=device_index,
                channels=2,
                samplerate=44100,
                blocksize=2048
            )
            stream.start()
            print("  ✓ Input stream started successfully")
            stream.stop()
            stream.close()
            print("  ✓ Input stream stopped successfully")
        
        # Try to open output stream
        if device['max_output_channels'] >= 2:
            print("Testing OUTPUT stream...")
            stream = sd.OutputStream(
                device=device_index,
                channels=2,
                samplerate=44100,
                blocksize=2048
            )
            stream.start()
            print("  ✓ Output stream started successfully")
            stream.stop()
            stream.close()
            print("  ✓ Output stream stopped successfully")
        
        print("\n✓ Device test passed!")
        return True
        
    except Exception as e:
        print(f"\n✗ Device test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\nAudio Device Diagnostics")
    print("=" * 80)
    
    # List all devices
    list_devices()
    
    # Interactive testing
    while True:
        print("\n" + "=" * 80)
        print("Options:")
        print("1. Test a specific device")
        print("2. Refresh device list")
        print("3. Exit")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            device_num = input("Enter device number to test: ").strip()
            try:
                device_index = int(device_num)
                test_device(device_index)
            except ValueError:
                print("Invalid device number")
            except Exception as e:
                print(f"Error: {e}")
        
        elif choice == "2":
            list_devices()
        
        elif choice == "3":
            print("\nExiting...")
            break
        
        else:
            print("Invalid choice")

if __name__ == '__main__':
    main()