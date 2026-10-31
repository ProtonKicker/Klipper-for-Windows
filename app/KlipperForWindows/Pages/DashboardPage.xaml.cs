using KlipperForWindows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.UI;

namespace KlipperForWindows.Pages;

public sealed partial class DashboardPage : Page
{
    private bool _busy;
    private List<SerialPortInfo>? _ports;

    public DashboardPage()
    {
        InitializeComponent();
        UiBus.StatusChanged += OnStatus;
        LanToggle.Toggled += (_, _) => { };
        OnStatus();
    }

    private void OnStatus()
    {
        var snap = UiBus.Latest;
        if (snap is null)
        {
            if (!Cli.Installed)
                SetupBanner.Visibility = Visibility.Visible;
            return;
        }

        VersionText.Text = "Klipper for Windows app  ·  CLI v" + snap.Version +
                           "  ·  data: " + snap.Data;

        SetupBanner.Visibility = Cli.Installed ? Visibility.Collapsed : Visibility.Visible;

        bool up = snap.StackUp;
        StackDot.Fill = new SolidColorBrush(up ? Color.FromArgb(255, 46, 160, 67)
                                              : Color.FromArgb(255, 154, 154, 154));
        StackText.Text = up ? "Running" : "Stopped";
        StartBtn.IsEnabled = !up && !_busy;
        StopBtn.IsEnabled = up && !_busy;
        RestartBtn.IsEnabled = up && !_busy;
        KillBtn.IsEnabled = up && !_busy;
        ActionRing.IsActive = _busy;

        SetDot(DotKlipper, snap.Services.GetValueOrDefault("klipper"));
        SetDot(DotMoonraker, snap.Services.GetValueOrDefault("moonraker"));
        SetDot(DotMainsail, snap.Services.GetValueOrDefault("web_mainsail"));
        SetDot(DotFluidd, snap.Services.GetValueOrDefault("web_fluidd"));
        SetDot(DotGuard, snap.Services.GetValueOrDefault("sleep_guard"));
        SetDot(DotWatchdog, snap.Services.GetValueOrDefault("watchdog"));

        KlippyState.Text = snap.KlippyConnected ? snap.KlippyState : "disconnected";
        KlippyState.Foreground = new SolidColorBrush(
            snap.KlippyState == "ready" ? Color.FromArgb(255, 46, 160, 67)
            : snap.KlippyState == "error" || snap.KlippyState == "shutdown"
                ? Color.FromArgb(255, 200, 60, 50)
                : Color.FromArgb(255, 154, 154, 154));
        KlippyMsg.Text = snap.StateMessage;

        CurrentPort.Text = snap.Serial ?? "not set";
        LanText.Text = "LAN access: " + (snap.Lan ? "on" : "off");
        LanToggle.Toggled -= Lan_Toggled;
        LanToggle.IsOn = snap.Lan;
        LanToggle.Toggled += Lan_Toggled;
        LanHint.Text = snap.Lan
            ? (snap.LanIp is null
                ? "Other devices on your network can reach the stack."
                : $"From other devices: http://{snap.LanIp}:8080 (Mainsail), :8081 (Fluidd), :7125 (API).")
            : "Only this PC can reach the stack (localhost).";
    }

    private static void SetDot(Ellipse dot, bool on) =>
        dot.Fill = new SolidColorBrush(on ? Color.FromArgb(255, 46, 160, 67)
                                         : Color.FromArgb(255, 154, 154, 154));

    private async Task RunBusyAsync(Func<Task<string>> action)
    {
        if (_busy) return;
        _busy = true;
        OnStatus();
        try
        {
            await action();
            await Task.Delay(800);
            UiBus.Publish(await Cli.StatusAsync());
        }
        catch (Exception ex)
        {
            var dlg = new ContentDialog
            {
                Title = "Command failed",
                Content = ex.Message,
                CloseButtonText = "OK",
                XamlRoot = Content.XamlRoot,
            };
            await dlg.ShowAsync();
        }
        finally
        {
            _busy = false;
            OnStatus();
        }
    }

    private void Start_Click(object sender, RoutedEventArgs e) => _ = RunBusyAsync(Cli.UpAsync);
    private void Stop_Click(object sender, RoutedEventArgs e) => _ = RunBusyAsync(Cli.DownAsync);
    private void Restart_Click(object sender, RoutedEventArgs e) => _ = RunBusyAsync(Cli.RestartAsync);
    private void Kill_Click(object sender, RoutedEventArgs e) => _ = RunBusyAsync(async () =>
        await Cli.RunAsync("killall"));

    private async Task RefreshPortsAsync()
    {
        _ports = await Cli.SerialListAsync();
        PortBox.Items.Clear();
        foreach (var p in _ports)
            PortBox.Items.Add($"{p.Path}  —  {p.Description}");
    }

    private void RefreshPorts_Click(object sender, RoutedEventArgs e) => _ = RefreshPortsAsync();

    private async void AutoPort_Click(object sender, RoutedEventArgs e)
    {
        await RunBusyAsync(Cli.SerialAutoAsync);
        await RefreshPortsAsync();
    }

    private async void ApplyPort_Click(object sender, RoutedEventArgs e)
    {
        var sel = PortBox.SelectedItem as string;
        if (sel is null) return;
        var port = sel.Split(' ')[0];
        await RunBusyAsync(() => Cli.SerialSetAsync(port));
    }

    private async void Lan_Toggled(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        await RunBusyAsync(() => Cli.LanAsync(LanToggle.IsOn));
    }

    private void OpenMainsail_Click(object sender, RoutedEventArgs e) => Launch("http://localhost:8080");
    private void OpenFluidd_Click(object sender, RoutedEventArgs e) => Launch("http://localhost:8081");

    private static void Launch(string url)
    {
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

    private async void RunSetup_Click(object sender, RoutedEventArgs e)
    {
        RunSetupBtn.IsEnabled = false;
        SetupRing.IsActive = true;
        SetupLog.Visibility = Visibility.Visible;
        SetupLog.Text = "Fetching components (this downloads Klipper, Moonraker and the web UIs)...";
        try
        {
            // Setup runs with a system python (the venv does not exist yet);
            // the CLI itself needs nothing beyond the standard library.
            string[] candidates = { "python", "py" };
            string args = "-m klipperforwindows setup";
            System.Diagnostics.Process? proc = null;
            foreach (var exe in candidates)
            {
                try
                {
                    var psi = new System.Diagnostics.ProcessStartInfo
                    {
                        FileName = exe,
                        Arguments = exe == "py" ? "-3 " + args : args,
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                    };
                    proc = System.Diagnostics.Process.Start(psi);
                    if (proc is not null) break;
                }
                catch { }
            }
            if (proc is null)
                throw new InvalidOperationException(
                    "No Python found on PATH. Install Python 3.10+ from python.org first.");
            var stdoutTask = proc.StandardOutput.ReadToEndAsync();
            var stderrTask = proc.StandardError.ReadToEndAsync();
            await proc.WaitForExitAsync();
            var outText = (await stdoutTask) + (await stderrTask);
            SetupLog.Text = outText.Length > 3000 ? "..." + outText[^3000..] : outText;
            if (proc.ExitCode == 0)
            {
                SetupBanner.Visibility = Visibility.Collapsed;
                UiBus.Publish(await Cli.StatusAsync());
            }
        }
        catch (Exception ex)
        {
            SetupLog.Text = "Setup failed: " + ex.Message;
        }
        finally
        {
            RunSetupBtn.IsEnabled = true;
            SetupRing.IsActive = false;
        }
    }
}
