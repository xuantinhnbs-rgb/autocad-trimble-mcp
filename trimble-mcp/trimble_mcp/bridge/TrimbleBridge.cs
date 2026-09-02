// TrimbleBridge - cau noi giua MCP server (Python) va Trimble Connect for Desktop.
//
// Giao thuc: JSON-lines tren stdin/stdout (UTF-8).
//   vao : {"id": 1, "cmd": "status", "args": {}}
//   ra  : {"id": 1, "ok": true, "result": {...}}
//         {"id": 1, "ok": false, "error": "..."}
//
// Bien dich bang csc.exe cua .NET Framework 4.8 (co san trong Windows), xem build.py.
// Vi the ma nguon giu o muc C# 5: khong dung string interpolation, ?., nameof...

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using System.Web.Script.Serialization;

namespace TrimbleBridge
{
    public static class Program
    {
        internal const string DefaultInstallDir = @"C:\Program Files\Trimble\Trimble Connect";

        internal static string InstallDir;
        internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

        private static StreamWriter _out;

        public static int Main(string[] args)
        {
            Json.MaxJsonLength = int.MaxValue;
            Json.RecursionLimit = 200;

            InstallDir = ResolveInstallDir(args);
            AppDomain.CurrentDomain.AssemblyResolve += OnAssemblyResolve;

            var stdin = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));
            _out = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false));
            _out.AutoFlush = true;

            string line;
            while ((line = stdin.ReadLine()) != null)
            {
                line = line.Trim();
                if (line.Length == 0) continue;
                HandleLine(line);
            }

            Shutdown();
            return 0;
        }

        // Tach rieng khoi Main: cac lenh cham vao kieu cua Trimble nen chi duoc JIT
        // sau khi AssemblyResolve o tren da duoc gan.
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void HandleLine(string line)
        {
            object id = null;
            try
            {
                var req = Json.Deserialize<Dictionary<string, object>>(line);
                if (req == null) throw new Exception("Request khong phai JSON object.");
                req.TryGetValue("id", out id);

                string cmd = Args.Str(req, "cmd", null);
                if (string.IsNullOrEmpty(cmd)) throw new Exception("Thieu truong cmd.");

                object rawArgs;
                req.TryGetValue("args", out rawArgs);
                var a = rawArgs as Dictionary<string, object>;
                if (a == null) a = new Dictionary<string, object>();

                object result = Session.Dispatch(cmd, a);
                Reply(new Dictionary<string, object> { { "id", id }, { "ok", true }, { "result", result } });
            }
            catch (Exception ex)
            {
                Reply(new Dictionary<string, object>
                {
                    { "id", id },
                    { "ok", false },
                    { "error", Flatten(ex) },
                    { "error_type", ex.GetType().Name },
                });
            }
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void Shutdown()
        {
            try { Session.Cleanup(); }
            catch { }
        }

        private static void Reply(Dictionary<string, object> payload)
        {
            string text;
            try
            {
                text = Json.Serialize(payload);
            }
            catch (Exception ex)
            {
                object id = payload.ContainsKey("id") ? payload["id"] : null;
                text = Json.Serialize(new Dictionary<string, object>
                {
                    { "id", id },
                    { "ok", false },
                    { "error", "Khong serialize duoc ket qua: " + ex.Message },
                });
            }
            _out.WriteLine(text);
        }

        internal static string Flatten(Exception ex)
        {
            var parts = new List<string>();
            while (ex != null)
            {
                parts.Add(ex.Message);
                ex = ex.InnerException;
            }
            return string.Join(" | ", parts.ToArray());
        }

        private static string ResolveInstallDir(string[] args)
        {
            for (int i = 0; i < args.Length - 1; i++)
                if (args[i] == "--install-dir") return args[i + 1];

            string env = Environment.GetEnvironmentVariable("TRIMBLE_CONNECT_DIR");
            if (!string.IsNullOrEmpty(env) && Directory.Exists(env)) return env;

            if (Directory.Exists(DefaultInstallDir)) return DefaultInstallDir;

            // Suy ra tu tien trinh dang chay, phong khi cai o o dia khac.
            try
            {
                foreach (var p in Process.GetProcessesByName("TrimbleConnect"))
                {
                    try
                    {
                        string exe = p.MainModule.FileName;
                        if (!string.IsNullOrEmpty(exe)) return Path.GetDirectoryName(exe);
                    }
                    catch { }
                }
            }
            catch { }

            return DefaultInstallDir;
        }

        private static readonly HashSet<string> Resolving = new HashSet<string>();

        private static Assembly OnAssemblyResolve(object sender, ResolveEventArgs e)
        {
            string name = new AssemblyName(e.Name).Name;

            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                if (asm.GetName().Name == name) return asm;

            if (!Resolving.Add(name)) return null;
            try
            {
                string path = Path.Combine(InstallDir, name + ".dll");
                if (File.Exists(path)) return Assembly.LoadFrom(path);
                return null;
            }
            finally
            {
                Resolving.Remove(name);
            }
        }
    }

    /// <summary>Doc tham so tu dictionary da giai ma tu JSON.</summary>
    internal static class Args
    {
        public static string Str(Dictionary<string, object> a, string key, string fallback)
        {
            object v;
            if (a == null || !a.TryGetValue(key, out v) || v == null) return fallback;
            string s = v as string;
            if (s == null) s = Convert.ToString(v, CultureInfo.InvariantCulture);
            return s.Length == 0 ? fallback : s;
        }

        public static string Required(Dictionary<string, object> a, string key)
        {
            string v = Str(a, key, null);
            if (v == null) throw new Exception("Thieu tham so bat buoc: " + key);
            return v;
        }

        public static double Dbl(Dictionary<string, object> a, string key, double fallback)
        {
            object v;
            if (a == null || !a.TryGetValue(key, out v) || v == null) return fallback;
            return Convert.ToDouble(v, CultureInfo.InvariantCulture);
        }

        public static double? DblOpt(Dictionary<string, object> a, string key)
        {
            object v;
            if (a == null || !a.TryGetValue(key, out v) || v == null) return null;
            return Convert.ToDouble(v, CultureInfo.InvariantCulture);
        }

        public static int Int(Dictionary<string, object> a, string key, int fallback)
        {
            object v;
            if (a == null || !a.TryGetValue(key, out v) || v == null) return fallback;
            return Convert.ToInt32(v, CultureInfo.InvariantCulture);
        }

        public static bool Bool(Dictionary<string, object> a, string key, bool fallback)
        {
            object v;
            if (a == null || !a.TryGetValue(key, out v) || v == null) return fallback;
            if (v is bool) return (bool)v;
            return Convert.ToBoolean(v, CultureInfo.InvariantCulture);
        }

        /// <summary>Doi mot mang JSON da giai ma thanh List.
        ///
        /// JavaScriptSerializer tra ve ArrayList chu khong phai object[] khi
        /// gia tri nam trong mot Dictionary&lt;string, object&gt;, nen khong duoc
        /// ep kieu thang sang object[].
        /// </summary>
        public static List<object> AsList(object v)
        {
            if (v == null || v is string) return null;
            var items = v as System.Collections.IEnumerable;
            if (items == null) return null;

            var list = new List<object>();
            foreach (var item in items) list.Add(item);
            return list;
        }

        public static List<string> StrList(Dictionary<string, object> a, string key)
        {
            var result = new List<string>();
            object v;
            if (a == null || !a.TryGetValue(key, out v) || v == null) return result;

            if (v is string)
            {
                result.Add((string)v);
                return result;
            }

            var arr = v as System.Collections.IEnumerable;
            if (arr == null)
            {
                result.Add(Convert.ToString(v, CultureInfo.InvariantCulture));
                return result;
            }
            foreach (var item in arr)
                if (item != null) result.Add(Convert.ToString(item, CultureInfo.InvariantCulture));
            return result;
        }

        public static List<string> RequiredList(Dictionary<string, object> a, string key)
        {
            var v = StrList(a, key);
            if (v.Count == 0) throw new Exception("Thieu tham so bat buoc (danh sach rong): " + key);
            return v;
        }

        public static T AsEnum<T>(Dictionary<string, object> a, string key, T fallback) where T : struct
        {
            string raw = Str(a, key, null);
            if (raw == null) return fallback;

            string s = raw.Replace("_", "").Replace("-", "").Replace(" ", "");
            foreach (var name in Enum.GetNames(typeof(T)))
                if (string.Equals(name, s, StringComparison.OrdinalIgnoreCase))
                    return (T)Enum.Parse(typeof(T), name);

            throw new Exception("Gia tri '" + raw + "' khong hop le cho " + key +
                                ". Cho phep: " + string.Join(", ", Enum.GetNames(typeof(T))));
        }

        public static Color AsColor(Dictionary<string, object> a, string key)
        {
            object v;
            if (a == null || !a.TryGetValue(key, out v) || v == null)
                throw new Exception("Thieu tham so mau: " + key);

            var arr = AsList(v);
            if (arr != null && arr.Count >= 3)
                return Color.FromArgb(
                    Convert.ToInt32(arr[0], CultureInfo.InvariantCulture),
                    Convert.ToInt32(arr[1], CultureInfo.InvariantCulture),
                    Convert.ToInt32(arr[2], CultureInfo.InvariantCulture));

            string s = Convert.ToString(v, CultureInfo.InvariantCulture).Trim();
            if (s.Contains(","))
            {
                var p = s.Split(',');
                if (p.Length >= 3)
                    return Color.FromArgb(
                        int.Parse(p[0].Trim(), CultureInfo.InvariantCulture),
                        int.Parse(p[1].Trim(), CultureInfo.InvariantCulture),
                        int.Parse(p[2].Trim(), CultureInfo.InvariantCulture));
            }
            return ColorTranslator.FromHtml(s);
        }
    }
}
