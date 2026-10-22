using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class QuestionStudioLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string pythonw = Path.Combine(root, "runtime", "python", "pythonw.exe");
        string desktopScript = Path.Combine(root, "app", "desktop.py");
        string codex = Path.Combine(root, "runtime", "codex", "codex.exe");
        string node = Path.Combine(root, "runtime", "node", "node.exe");

        if (!File.Exists(pythonw) || !File.Exists(desktopScript))
        {
            MessageBox.Show(
                "Question Studio could not find its bundled Python runtime or desktop entry point.\r\n\r\n" +
                "Try repairing the installation from Windows Settings > Apps.",
                "Question Studio",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 2;
        }

        try
        {
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = pythonw;
            start.Arguments = QuoteWindowsArgument(desktopScript);
            foreach (string argument in args)
                start.Arguments += " " + QuoteWindowsArgument(argument);
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.WindowStyle = ProcessWindowStyle.Hidden;
            start.EnvironmentVariables["QUESTION_STUDIO_INSTALLED"] = "1";
            start.EnvironmentVariables["QUESTION_STUDIO_APP_ROOT"] = root;
            start.EnvironmentVariables["QUESTION_STUDIO_CODEX_PATH"] = codex;
            start.EnvironmentVariables["QUESTION_STUDIO_CODEX_MANIFEST"] = Path.Combine(root, "runtime", "codex", "manifest.json");
            start.EnvironmentVariables["QUESTION_STUDIO_NODE_PATH"] = node;
            start.EnvironmentVariables["QUESTION_STUDIO_PYTHON_PATH"] = pythonw;
            if (File.Exists(node))
            {
                string existingPath = start.EnvironmentVariables["PATH"] ?? Environment.GetEnvironmentVariable("PATH") ?? "";
                start.EnvironmentVariables["PATH"] = Path.GetDirectoryName(node) + Path.PathSeparator + existingPath;
            }

            Process child = Process.Start(start);
            if (child == null)
                throw new InvalidOperationException("Windows did not start the Python runtime.");
            if (child.WaitForExit(2500) && child.ExitCode != 0)
            {
                int exitCode = child.ExitCode;
                child.Dispose();
                MessageBox.Show(
                    "Question Studio stopped while starting (exit code " + exitCode.ToString() + ").\r\n\r\n" +
                    "Try repairing the installation from Windows Settings > Apps. If the problem continues, contact support with the time this message appeared.",
                    "Question Studio",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 1;
            }
            child.Dispose();
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "Question Studio could not start.\r\n\r\n" + error.Message +
                "\r\n\r\nTry repairing the installation from Windows Settings > Apps.",
                "Question Studio",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }
    }

    // Quote one argument using the Windows C runtime parsing rules. Doubling
    // backslashes before quotes and before the closing quote preserves spaces,
    // quotes, and paths that end in a backslash without invoking a shell.
    private static string QuoteWindowsArgument(string value)
    {
        StringBuilder result = new StringBuilder();
        result.Append('"');
        int backslashes = 0;
        foreach (char character in value)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }
            if (character == '"')
            {
                result.Append('\\', backslashes * 2 + 1);
                result.Append('"');
                backslashes = 0;
                continue;
            }
            if (backslashes > 0)
            {
                result.Append('\\', backslashes);
                backslashes = 0;
            }
            result.Append(character);
        }
        result.Append('\\', backslashes * 2);
        result.Append('"');
        return result.ToString();
    }
}
