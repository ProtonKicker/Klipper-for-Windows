using KlipperForWindows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.IO;

namespace KlipperForWindows.Pages;

public sealed partial class ConfigPage : Page
{
    private string PrinterCfg => Path.Combine(Cli.DataFolder, "config", "printer.cfg");
    private string MoonrakerCfg => Path.Combine(Cli.DataFolder, "config", "moonraker.conf");

    public ConfigPage()
    {
        InitializeComponent();
        ConfigPivot.SelectionChanged += (_, _) => _ = LoadAsync();
        Loaded += (_, _) => _ = LoadAsync();
    }

    private string CurrentFile =>
        ConfigPivot.SelectedIndex == 1 ? MoonrakerCfg : PrinterCfg;

    private async Task LoadAsync()
    {
        try
        {
            Editor.Text = File.Exists(CurrentFile)
                ? await File.ReadAllTextAsync(CurrentFile)
                : $"(file not found: {CurrentFile} — run setup first)";
        }
        catch (Exception ex)
        {
            Editor.Text = "(failed to read: " + ex.Message + ")";
        }
    }

    private void Load_Click(object sender, RoutedEventArgs e) => _ = LoadAsync();

    private async Task SaveAsync()
    {
        BusyRing.IsActive = true;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(CurrentFile)!);
            await File.WriteAllTextAsync(CurrentFile, Editor.Text);
        }
        finally
        {
            BusyRing.IsActive = false;
        }
    }

    private void Save_Click(object sender, RoutedEventArgs e) => _ = SaveAsync();

    private async void SaveRestart_Click(object sender, RoutedEventArgs e)
    {
        await SaveAsync();
        await Cli.RestartKlipperAsync();
        var dlg = new ContentDialog
        {
            Title = "Saved",
            Content = "Configuration saved and the Klipper host is restarting. " +
                      "It takes a few seconds to come back ready.",
            CloseButtonText = "OK",
            XamlRoot = Content.XamlRoot,
        };
        await dlg.ShowAsync();
    }
}
