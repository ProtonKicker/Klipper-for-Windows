using Microsoft.UI.Xaml;
using System.IO;

namespace KlipperForWindows;

public partial class App : Application
{
    public static Window? MainWindow { get; private set; }

    public static string LogPath => System.IO.Path.Combine(
        System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData),
        "KlipperForWindows", "app-log.txt");

    public static void Log(string msg)
    {
        try
        {
            File.AppendAllText(LogPath,
                DateTime.Now.ToString("HH:mm:ss.fff ") + msg + "\n");
        }
        catch { }
    }

    public App()
    {
        InitializeComponent();
        UnhandledException += (_, e) =>
        {
            Log("UNHANDLED: " + e.Message + "\n" + e.Exception);
            e.Handled = true;
        };
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        // Keep the WebView2 profile out of the (possibly OneDrive-synced)
        // install folder: file-sync locks corrupt browser profiles
        var dataFolder = System.IO.Path.Combine(
            System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData),
            "KlipperForWindows", "webview2");
        System.IO.Directory.CreateDirectory(dataFolder);
        Environment.SetEnvironmentVariable("WEBVIEW2_USER_DATA_FOLDER", dataFolder);
        Log("app launched (webview2 profile: " + dataFolder + ")");
        MainWindow = new MainWindow();
        MainWindow.Activate();
    }
}
