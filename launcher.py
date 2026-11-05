import multiprocessing

if __name__ == "__main__":
    # Required so that frozen child processes (used by the prep pipeline)
    # re-enter the right target function instead of relaunching the GUI.
    multiprocessing.freeze_support()
    from apollo.dev_gui import main
    main()
