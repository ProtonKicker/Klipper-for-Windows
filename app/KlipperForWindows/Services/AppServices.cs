using System.Diagnostics;
using System.IO;
using System.Text.Json;

namespace KlipperForWindows.Services;

/// <summary>Snapshot of `klipperforwindows status --json`.</summary>
public sealed class StatusSnapshot
{
    public Dictionary<string, bool> Services { get; set; } = new();
    public bool KlippyConnected { get; set; }
    public string KlippyState { get; set; } = "unknown";
    public string StateMessage { get; set; } = "";
    public string? Serial { get; set; }
    public string Data { get; set; } = "";
    public string AppHome { get; set; } = "";
    public string Ui { get; set; } = "mainsail";
    public bool Lan { get; set; }
    public string? LanIp { get; set; }
    public string Version { get; set; } = "";
    public List<UpdateInfo> Updates { get; set; } = new();
    public Dictionary<string, string> Urls { get; set; } = new();

    public bool StackUp => Services.Values.Any(v => v);
}

public sealed class UpdateInfo
{
    public string Component { get; set; } = "";
    public string Pinned { get; set; } = "";
    public string Latest { get; set; } = "";
}

public sealed class SerialPortInfo
{
    public string Path { get; set; } = "";
    public string Description { get; set; } = "";
}

/// <summary>Bridge to the klipperforwindows CLI (same commands the console uses).</summary>
public static class Cli
{
    public static string AppHome =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "KlipperForWindows");

    public static string PythonExe => Path.Combine(AppHome, "venv", "Scripts", "python.exe");

    public static bool Installed => File.Exists(PythonExe);

    public static string DataFolder =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "Klipper for Windows");

    public static async Task<string> RunAsync(params string[] args)
    {
        App.Log("RunAsync start: " + string.Join(' ', args));
        var psi = new ProcessStartInfo
        {
            FileName = PythonExe,
            Arguments = "-m klipperforwindows " + string.Join(' ',
                args.Select(a => a.Contains(' ') ? "\"" + a + "\"" : a)),
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        using var proc = Process.Start(psi)!;
        var stdoutTask = proc.StandardOutput.ReadToEndAsync();
        var stderrTask = proc.StandardError.ReadToEndAsync();
        var exitTask = proc.WaitForExitAsync();
        var done = await Task.WhenAny(exitTask,
            Task.Delay(TimeSpan.FromSeconds(30)));
        if (done != exitTask)
        {
            App.Log("RunAsync TIMEOUT: " + string.Join(' ', args));
            try { proc.Kill(true); } catch { }
            throw new TimeoutException("CLI did not finish within 30s: " +
                string.Join(' ', args));
        }
        string stdout = await stdoutTask;
        await stderrTask;
        App.Log("RunAsync done: " + string.Join(' ', args) +
                " exit=" + proc.ExitCode);
        return stdout;
    }

    public static async Task<StatusSnapshot?> StatusAsync()
    {
        try
        {
            var json = await RunAsync("status", "--json");
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            var snap = new StatusSnapshot
            {
                KlippyConnected = root.GetProperty("klippy_connected").GetBoolean(),
                KlippyState = root.GetProperty("klippy_state").GetString() ?? "unknown",
                StateMessage = root.GetProperty("state_message").GetString() ?? "",
                Serial = root.TryGetProperty("serial", out var s) && s.ValueKind == JsonValueKind.String
                    ? s.GetString() : null,
                Data = root.GetProperty("data").GetString() ?? "",
                AppHome = root.GetProperty("app_home").GetString() ?? "",
                Ui = root.GetProperty("ui").GetString() ?? "mainsail",
                Lan = root.GetProperty("lan").GetBoolean(),
                LanIp = root.TryGetProperty("lan_ip", out var ip) && ip.ValueKind == JsonValueKind.String
                    ? ip.GetString() : null,
                Version = root.GetProperty("version").GetString() ?? "",
            };
            foreach (var kv in root.GetProperty("services").EnumerateObject())
                snap.Services[kv.Name] = kv.Value.GetBoolean();
            foreach (var kv in root.GetProperty("urls").EnumerateObject())
                snap.Urls[kv.Name] = kv.Value.GetString() ?? "";
            if (root.TryGetProperty("updates", out var ups) && ups.ValueKind == JsonValueKind.Array)
            {
                foreach (var u in ups.EnumerateArray())
                {
                    snap.Updates.Add(new UpdateInfo
                    {
                        Component = u.GetProperty("component").GetString() ?? "",
                        Pinned = u.GetProperty("pinned").GetString() ?? "",
                        Latest = u.GetProperty("latest").GetString() ?? "",
                    });
                }
            }
            return snap;
        }
        catch
        {
            return null;
        }
    }

    public static async Task<List<SerialPortInfo>> SerialListAsync()
    {
        var list = new List<SerialPortInfo>();
        try
        {
            var json = await RunAsync("serial", "--json");
            using var doc = JsonDocument.Parse(json);
            foreach (var p in doc.RootElement.GetProperty("ports").EnumerateArray())
            {
                list.Add(new SerialPortInfo
                {
                    Path = p.GetProperty("path").GetString() ?? "",
                    Description = p.GetProperty("description").GetString() ?? "",
                });
            }
        }
        catch { }
        return list;
    }

    public static Task<string> UpAsync() => RunAsync("up");
    public static Task<string> DownAsync() => RunAsync("down");
    public static Task<string> RestartAsync() => RunAsync("restart");
    public static Task<string> RestartKlipperAsync() => RunAsync("restart-klipper");
    public static Task<string> SerialAutoAsync() => RunAsync("serial", "--auto");
    public static Task<string> SerialSetAsync(string port) => RunAsync("serial", "--set", port);
    public static Task<string> LanAsync(bool on) => RunAsync("lan", on ? "on" : "off");
    public static Task<string> SetUiAsync(string name) => RunAsync("ui", name);
}
