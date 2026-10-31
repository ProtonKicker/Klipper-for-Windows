using KlipperForWindows.Pages;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace KlipperForWindows;

public sealed class UiBus
{
    public static event Action? StatusChanged;
    public static Services.StatusSnapshot? Latest { get; private set; }
    public static void Publish(Services.StatusSnapshot? snap)
    {
        Latest = snap;
        StatusChanged?.Invoke();
    }
}

public sealed partial class MainWindow : Window
{
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(2) };

    private string? _pendingPage;

    public MainWindow()
    {
        InitializeComponent();
        Title = "Klipper for Windows";
        try
        {
            AppWindow.SetIcon(System.IO.Path.Combine(
                AppContext.BaseDirectory, "Assets", "appicon.ico"));
        }
        catch { }
        try
        {
            SystemBackdrop = new MicaBackdrop { Kind = Microsoft.UI.Composition.SystemBackdrops.MicaKind.BaseAlt };
        }
        catch { }
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(null);
        Nav.SelectedItem = Nav.MenuItems[0];
        var pageArg = Array.FindIndex(Environment.GetCommandLineArgs(),
            a => a.Equals("--page", StringComparison.OrdinalIgnoreCase));
        if (pageArg >= 0 && pageArg + 1 < Environment.GetCommandLineArgs().Length)
            _pendingPage = Environment.GetCommandLineArgs()[pageArg + 1];
        ContentFrame.Loaded += (_, _) =>
        {
            // Navigate after the window/XAML tree is fully up; constructing
            // the WebView2 page too early crashes the process
            if (_pendingPage is not null)
            {
                NavigateTo(_pendingPage);
                _pendingPage = null;
            }
        };
        _timer.Tick += async (_, _) => UiBus.Publish(await Services.Cli.StatusAsync());
        _timer.Start();
        _ = PollOnceAsync();
    }

    private void NavigateTo(string tag)
    {
        foreach (var item in Nav.MenuItems.OfType<NavigationViewItem>())
        {
            if ((string)item.Tag == tag)
            {
                Nav.SelectedItem = item;
                return;
            }
        }
    }

    private async Task PollOnceAsync()
    {
        UiBus.Publish(await Services.Cli.StatusAsync());
    }

    private void Nav_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is not NavigationViewItem item || item.Tag is not string tag)
            return;
        App.Log("nav -> " + tag);
        try
        {
            switch (tag)
            {
                case "dashboard": ContentFrame.Navigate(typeof(DashboardPage)); break;
                case "printer": ContentFrame.Navigate(typeof(FrontendPage)); break;
                case "config": ContentFrame.Navigate(typeof(ConfigPage)); break;
                case "logs": ContentFrame.Navigate(typeof(LogsPage)); break;
                case "settings": ContentFrame.Navigate(typeof(SettingsPage)); break;
            }
            App.Log("nav ok -> " + tag);
        }
        catch (Exception ex)
        {
            App.Log("nav FAILED -> " + tag + ": " + ex);
        }
    }
}
