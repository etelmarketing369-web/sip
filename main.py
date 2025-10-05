#!/usr/bin/env python3
"""
Windows Desktop SIP Dialer
Main entry point for the application
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox
import threading

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from sip_dialer import SipDialerApp
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure all required modules are available")
    sys.exit(1)

def main():
    """Main function to start the SIP Dialer application"""
    try:
        # Initialize the main window
        root = tk.Tk()
        root.title("Windows SIP Dialer - Account Status")
        root.geometry("800x600")
        root.minsize(600, 400)
        
        # Ensure the window is visible and focused (helps when launching from terminals or behind other windows)
        try:
            root.update_idletasks()
            root.deiconify()
            root.lift()
            root.focus_force()
            # Briefly set topmost to surface the window, then revert
            root.attributes("-topmost", True)
            root.after(1200, lambda: root.attributes("-topmost", False))
        except Exception:
            pass
        
        # Set window icon (if available)
        try:
            root.iconbitmap("icon.ico")
        except:
            pass  # Icon file not found, continue without it
        
        # Initialize and start the application
        app = SipDialerApp(root)
        try:
            print("GUI initialized; entering main loop")
        except Exception:
            pass
        
        # Start the GUI main loop
        root.mainloop()
        
    except Exception as e:
        messagebox.showerror("Error", f"Failed to start application: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
