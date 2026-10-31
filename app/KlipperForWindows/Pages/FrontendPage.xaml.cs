using KlipperForWindows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using Windows.UI;

namespace KlipperForWindows.Pages;

/// <summary>Hosts Mainsail or Fluidd in WebView2 (same-origin proxy ports).</summary>
public sealed partial class FrontendPage : Page
{
    private string _ui = "mainsail";
    private Microsoft.Web.WebView2.Core.CoreWebView2? _core;
    private bool _webViewReady;

    private bool _loadStarted;

    public FrontendPage()
    {
        InitializeComponent();
        UiBus.StatusChanged += OnStatus;
        // Create the WebView2 only after the page is in the visual tree;
        // constructing it earlier crashes WinUI
        Loaded += (_, _) =>
        {
            if (_loadStarted) return;
            _loadStarted = true;
            LoadWebview();
        };
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        if (e.Parameter is string ui && (ui == "mainsail" || ui == "fluidd"))
        {
            _ui = ui;
            foreach (ComboBoxItem item in UiSwitch.Items)
            {
                if ((string)item.Tag == ui)
                {
                    UiSwitch.SelectionChanged -= UiSwitch_SelectionChanged;
                    UiSwitch.SelectedItem = item;
                    UiSwitch.SelectionChanged += UiSwitch_SelectionChanged;
                    break;
                }
            }
        }
        NavigateUi();
    }

    private async void LoadWebview()
    {
        try
        {
            var webView = new Microsoft.UI.Xaml.Controls.WebView2();
            webView.NavigationCompleted += (_, _) => LoadRing.IsActive = false;
            HostGrid.Children.Insert(0, webView);
            await webView.EnsureCoreWebView2Async();
            _core = webView.CoreWebView2;
            webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
            webView.CoreWebView2.Settings.IsStatusBarEnabled = false;
            _webViewReady = true;
            NavigateUi();
        }
        catch (Exception ex)
        {
            NotRunningHint.Text = "WebView2 failed to initialize: " + ex.Message;
            NotRunningHint.Visibility = Visibility.Visible;
            LoadRing.IsActive = false;
        }
    }

    private void NavigateUi()
    {
        if (!_webViewReady) return;
        var webView = HostGrid.Children.OfType<Microsoft.UI.Xaml.Controls.WebView2>().FirstOrDefault();
        if (webView is null) return;
        var url = _ui == "mainsail" ? "http://localhost:8080/" : "http://localhost:8081/";
        LoadRing.IsActive = true;
        webView.Source = new Uri(url);
    }

    private void OnStatus()
    {
        if (StatusHint is null || NotRunningHint is null)
            return;
        try
        {
            var snap = UiBus.Latest;
            bool running = snap?.Services.GetValueOrDefault(
                _ui == "mainsail" ? "web_mainsail" : "web_fluidd") ?? false;
            StatusHint.Text = running
                ? (snap?.KlippyState == "ready" ? "Printer connected" : "Stack running")
                : "Stack stopped";
            StatusHint.Foreground = new SolidColorBrush(running
                ? Color.FromArgb(255, 46, 160, 67) : Color.FromArgb(255, 154, 154, 154));
            NotRunningHint.Visibility = running ? Visibility.Collapsed : Visibility.Visible;
        }
        catch (Exception ex)
        {
            App.Log("OnStatus error: " + ex.Message);
        }
    }

    private void UiSwitch_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (UiSwitch is null || HostGrid is null)
            return; // still parsing XAML
        if (UiSwitch.SelectedItem is ComboBoxItem item && item.Tag is string tag)
        {
            _ui = tag;
            NavigateUi();
            OnStatus();
        }
    }

    private void Reload_Click(object sender, RoutedEventArgs e)
    {
        var webView = HostGrid.Children.OfType<Microsoft.UI.Xaml.Controls.WebView2>().FirstOrDefault();
        webView?.Reload();
    }

    private void OpenExternal_Click(object sender, RoutedEventArgs e)
    {
        var url = _ui == "mainsail" ? "http://localhost:8080/" : "http://localhost:8081/";
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true,
            });
        }
        catch { }
    }
}
