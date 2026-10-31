using KlipperForWindows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Diagnostics;
using System.IO;

namespace KlipperForWindows.Pages;

public sealed partial class SettingsPage : Page
{
    public SettingsPage()
    {
        InitializeComponent();
        DataPath.Text = Cli.DataFolder;
        AppHomePath.Text = Cli.AppHome;
        AboutText.Text = "Klipper for Windows runs pinned upstream Klipper, Moonraker, " +
                         "Mainsail and Fluidd natively on Windows — no virtual machine. " +
                         "Klipper's C helper is compiled with zig; the serial port is bridged " +
                         "to the C engine over a loopback socket; Moonraker reaches Klippy over " +
                         "TCP loopback; both web UIs are served by a local reverse proxy.";
        RefreshUiChoice();
        UiBus.StatusChanged += RefreshUiChoice;
    }

    private void RefreshUiChoice()
    {
        var ui = UiBus.Latest?.Ui ?? "mainsail";
        for (int i = 0; i < UiChoice.Items.Count; i++)
        {
            if (UiChoice.Items[i] is RadioButton rb && (string)rb.Tag == ui)
            {
                UiChoice.SelectionChanged -= UiChoice_SelectionChanged;
                UiChoice.SelectedIndex = i;
                UiChoice.SelectionChanged += UiChoice_SelectionChanged;
                break;
            }
        }
    }

    private async void UiChoice_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (UiChoice.SelectedItem is RadioButton rb && rb.Tag is string tag)
            await Cli.SetUiAsync(tag);
    }

    private void OpenData_Click(object sender, RoutedEventArgs e) => Open(Cli.DataFolder);
    private void OpenAppHome_Click(object sender, RoutedEventArgs e) => Open(Cli.AppHome);

    private static void Open(string path)
    {
        if (Directory.Exists(path))
            Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true });
    }

    private async void Doctor_Click(object sender, RoutedEventArgs e)
    {
        BusyRing.IsActive = true;
        DoctorOutput.Text = "Checking...";
        try
        {
            DoctorOutput.Text = await Cli.RunAsync("doctor");
        }
        catch (Exception ex)
        {
            DoctorOutput.Text = "failed: " + ex.Message;
        }
        finally
        {
            BusyRing.IsActive = false;
        }
    }

    private async void Update_Click(object sender, RoutedEventArgs e)
    {
        BusyRing.IsActive = true;
        DoctorOutput.Text = "Checking for updates...";
        try
        {
            var outText = await Cli.RunAsync("status");
            var lines = outText.Split('\n');
            var updates = lines.Where(l => l.TrimStart().StartsWith("update")).ToList();
            DoctorOutput.Text = updates.Count > 0
                ? "Updates available:\n" + string.Join('\n', updates)
                : "Everything is up to date.";
        }
        catch (Exception ex)
        {
            DoctorOutput.Text = "failed: " + ex.Message;
        }
        finally
        {
            BusyRing.IsActive = false;
        }
    }
}
