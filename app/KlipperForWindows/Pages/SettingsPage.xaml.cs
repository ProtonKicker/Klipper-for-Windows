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
                         "TCP loopback; the selected web UI is served by a local reverse proxy.";
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
        DoctorOutput.Text = "Checking upstream components (Klipper, Moonraker, Mainsail, Fluidd)...";
        try
        {
            var json = await Cli.RunAsync("status", "--json");
            using var doc = System.Text.Json.JsonDocument.Parse(json);
            var root = doc.RootElement;
            var pins = root.GetProperty("pins");
            var lines = new List<string>
            {
                "Installed component versions:",
                "  Klipper    " + pins.GetProperty("klipper").GetString(),
                "  Moonraker  " + pins.GetProperty("moonraker").GetString(),
                "  Mainsail   " + pins.GetProperty("mainsail").GetString(),
                "  Fluidd     " + pins.GetProperty("fluidd").GetString(),
            };
            if (root.TryGetProperty("updates", out var ups) &&
                ups.ValueKind == System.Text.Json.JsonValueKind.Array &&
                ups.GetArrayLength() > 0)
            {
                lines.Add("Updates available (apply with: " +
                          "python -m klipperforwindows setup --update):");
                foreach (var u in ups.EnumerateArray())
                {
                    lines.Add("  " + u.GetProperty("component").GetString() +
                              "  " + u.GetProperty("pinned").GetString() +
                              " -> " + u.GetProperty("latest").GetString());
                }
            }
            else
            {
                lines.Add("All components are at their pinned versions (up to date).");
            }
            DoctorOutput.Text = string.Join("\n", lines);
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
