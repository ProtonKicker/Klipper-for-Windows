using KlipperForWindows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Diagnostics;
using System.IO;

namespace KlipperForWindows.Pages;

public sealed partial class LogsPage : Page
{
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(3) };

    public LogsPage()
    {
        InitializeComponent();
        _timer.Tick += (_, _) => _ = LoadAsync();
        AutoRefresh.Toggled += (_, _) =>
        {
            if (AutoRefresh.IsOn) _timer.Start();
            else _timer.Stop();
        };
        _timer.Start();
        Loaded += (_, _) => _ = LoadAsync();
    }

    private string CurrentFile
    {
        get
        {
            var logs = Path.Combine(Cli.DataFolder, "logs");
            return LogSwitch.SelectedIndex == 1
                ? Path.Combine(logs, "moonraker.log")
                : Path.Combine(logs, "klippy.log");
        }
    }

    private async Task LoadAsync()
    {
        try
        {
            if (!File.Exists(CurrentFile))
            {
                LogText.Text = "(no log file yet: " + CurrentFile + ")";
                return;
            }
            using var stream = new FileStream(CurrentFile, FileMode.Open,
                FileAccess.Read, FileShare.ReadWrite);
            using var reader = new StreamReader(stream);
            var all = await reader.ReadToEndAsync();
            var lines = all.Split('\n');
            var tail = lines.Length > 400 ? lines[^400..] : lines;
            LogText.Text = string.Join('\n', tail);
            LogScroller.UpdateLayout();
            LogScroller.ChangeView(null, LogScroller.ScrollableHeight, null, disableAnimation: true);
        }
        catch (Exception ex)
        {
            LogText.Text = "(failed to read log: " + ex.Message + ")";
        }
    }

    private void LogSwitch_SelectionChanged(object sender, SelectionChangedEventArgs e)
        => _ = LoadAsync();

    private void Refresh_Click(object sender, RoutedEventArgs e) => _ = LoadAsync();

    private void OpenFolder_Click(object sender, RoutedEventArgs e)
    {
        var dir = Path.GetDirectoryName(CurrentFile);
        if (dir is not null && Directory.Exists(dir))
            Process.Start(new ProcessStartInfo { FileName = dir, UseShellExecute = true });
    }
}
