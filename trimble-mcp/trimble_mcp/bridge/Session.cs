// Session - toan bo phan cham vao Trimble Connect Desktop API.
// Tach khoi Program.cs de cac kieu cua Trimble chi duoc nap sau khi
// AppDomain.AssemblyResolve da san sang.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.Linq;
using System.Reflection;
using Trimble.Connect.Desktop.API;
using Trimble.Connect.Desktop.API.Common;
using Trimble.Connect.Desktop.API.Filters;
using Trimble.Connect.Desktop.API.ModelObjects;
using Trimble.Connect.Desktop.API.Models;
using Trimble.Connect.Desktop.API.Projects;
using Trimble.Connect.Desktop.API.Viewport;
using Trimble.Connect.Desktop.API.Views;
using TcAttribute = Trimble.Connect.Desktop.API.Attributes.Attribute;
using TcAttributeSet = Trimble.Connect.Desktop.API.Attributes.AttributeSet;

namespace TrimbleBridge
{
    internal static class Session
    {
        private const double DefaultTimeout = 15.0;
        private const int DefaultLimit = 500;

        private static TrimbleConnectDesktopClient _client;
        private static string _connectionName;
        private static Project _project;

        // ------------------------------------------------------------------
        // Dispatch
        // ------------------------------------------------------------------

        public static object Dispatch(string cmd, Dictionary<string, object> a)
        {
            switch (cmd)
            {
                // -- ket noi -------------------------------------------------
                case "ping": return Map("pong", true, "install_dir", Program.InstallDir);
                case "status": return Status(a);
                case "list_connections": return ListConnections(a);
                case "connect": return Connect(Args.Str(a, "connection_name", null), Args.Dbl(a, "timeout", DefaultTimeout));
                case "disconnect": Cleanup(); return Map("connected", false);
                case "start_app": return StartApp(a);
                case "refresh": DropProject(); return Status();

                // -- du an ---------------------------------------------------
                case "get_project": return ProjectInfo(Proj(a));

                // -- model ---------------------------------------------------
                case "list_models": return ListModels(a);
                case "load_models": return SetModelsLoaded(a, true);
                case "unload_models": return SetModelsLoaded(a, false);
                case "get_model_placement": return GetModelPlacement(a);
                case "set_model_placement": return SetModelPlacement(a);
                case "reset_model_placement": return ResetModelPlacement(a);
                case "get_model_content_path": return GetModelContentPath(a);

                // -- doi tuong -----------------------------------------------
                case "find_objects": return FindObjects(a);
                case "get_selection": return GetSelection(a);
                case "select_objects": return SelectObjects(a);
                case "set_visual_state": return SetVisualState(a);
                case "reset_visual_state": return ResetVisualState(a);
                case "set_color": return SetColor(a);
                case "reset_color": return ResetColor(a);
                case "isolate_objects": return IsolateObjects(a);
                case "reset_all": return ResetAll(a);
                case "get_object_attributes": return GetObjectAttributes(a);
                case "get_attribute_names": return GetAttributeNames(a);
                case "get_attribute": return GetAttribute(a);
                case "get_related_objects": return GetRelatedObjects(a);

                // -- view ----------------------------------------------------
                case "list_views": return ListViews(a);
                case "activate_view": return ActivateView(a);
                case "create_view": return CreateView(a);

                // -- viewport ------------------------------------------------
                case "get_camera": return GetCamera(a);
                case "set_camera": return SetCamera(a);
                case "zoom_to_objects": return ZoomToObjects(a);

                // -- cai dat -------------------------------------------------
                case "get_selection_mode": return Map("selection_mode", EnsureClient(a).SettingsManager.GetObjectSelectionMode().ToString());
                case "set_selection_mode": return SetSelectionMode(a);

                default:
                    throw new Exception("Lenh khong ho tro: " + cmd);
            }
        }

        // ------------------------------------------------------------------
        // Ket noi
        // ------------------------------------------------------------------

        private static object Status()
        {
            return Status(null);
        }

        private static object Status(Dictionary<string, object> a)
        {
            string connectError = null;
            if (_client == null && a != null && Args.Bool(a, "auto_connect", true))
            {
                try { EnsureClient(a); }
                catch (Exception ex) { connectError = Program.Flatten(ex); }
            }

            var result = Map(
                "connected", _client != null,
                "connection_name", _connectionName,
                "install_dir", Program.InstallDir,
                "desktop_running", Process.GetProcessesByName("TrimbleConnect").Length > 0);

            if (connectError != null) result["connect_error"] = connectError;

            if (_client != null)
            {
                try
                {
                    if (_project == null) LoadProject();
                    result["project"] = _project == null ? null : ProjectInfo(_project);
                    if (_project == null)
                        result["hint"] = "Da ket noi nhung chua co project nao dang mo. " +
                                         "Hay mo mot project trong Trimble Connect for Desktop.";
                }
                catch (Exception ex)
                {
                    result["project"] = null;
                    result["project_error"] = Program.Flatten(ex);
                }
            }
            return result;
        }

        private static object ListConnections(Dictionary<string, object> a)
        {
            double timeout = Args.Dbl(a, "timeout", DefaultTimeout);
            var probe = _client;
            var temp = probe == null ? new TrimbleConnectDesktopClient() : null;
            try
            {
                var src = (probe ?? temp).GetConnectionNames(timeout);
                var names = src == null ? new List<string>() : src.ToList();
                return Map("connections", names, "count", names.Count);
            }
            finally
            {
                if (temp != null) Free(temp);
            }
        }

        private static object Connect(string name, double timeout)
        {
            Cleanup();

            var client = new TrimbleConnectDesktopClient();
            bool ok;
            try
            {
                // Xac dinh ro instance de bao cao lai duoc ten ket noi thuc te.
                if (string.IsNullOrEmpty(name))
                {
                    var src = client.GetConnectionNames(timeout);
                    var found = src == null ? new List<string>() : src.ToList();
                    if (found.Count == 0)
                        throw new Exception(
                            "Khong tim thay instance nao cua Trimble Connect for Desktop. " +
                            "Hay mo ung dung va bat Desktop API trong Settings.");
                    name = found[0];
                }
                ok = client.Connect(name, timeout);
            }
            catch (Exception ex)
            {
                Free(client);
                throw new Exception("Ket noi that bai: " + Program.Flatten(ex));
            }

            if (!ok)
            {
                List<string> available;
                try
                {
                    var src = client.GetConnectionNames(2.0);
                    available = src == null ? new List<string>() : src.ToList();
                }
                catch { available = new List<string>(); }
                Free(client);

                string hint = available.Count > 0
                    ? " Cac ket noi dang co: " + string.Join(", ", available.ToArray()) + "."
                    : " Khong tim thay instance nao - hay mo Trimble Connect for Desktop va bat" +
                      " Settings > Extensions/API (Desktop API) roi thu lai.";
                throw new Exception("Khong ket noi duoc toi Trimble Connect for Desktop." + hint);
            }

            _client = client;
            _connectionName = name;
            _client.TrimbleConnectDesktopClosed += OnDesktopClosed;
            return Status();
        }

        private static object StartApp(Dictionary<string, object> a)
        {
            string definition = Args.Str(a, "connection_name", null);
            int wait = Args.Int(a, "wait_ms", 30000);

            var temp = _client ?? new TrimbleConnectDesktopClient();
            try
            {
                string actual = temp.StartApplication(definition, wait);
                if (string.IsNullOrEmpty(actual))
                    throw new Exception("Khong khoi dong duoc Trimble Connect for Desktop (khong lay duoc connection name).");
                return Map("connection_name", actual);
            }
            finally
            {
                if (!ReferenceEquals(temp, _client)) Free(temp);
            }
        }

        private static void OnDesktopClosed(object sender, EventArgs e)
        {
            _project = null;
            _client = null;
            _connectionName = null;
        }

        public static void Cleanup()
        {
            DropProject();
            if (_client != null)
            {
                try { _client.TrimbleConnectDesktopClosed -= OnDesktopClosed; }
                catch { }
                try { _client.Disconnect(); }
                catch { }
                Free(_client);
                _client = null;
            }
            _connectionName = null;
        }

        private static TrimbleConnectDesktopClient EnsureClient(Dictionary<string, object> a)
        {
            if (_client == null)
                Connect(Args.Str(a, "connection_name", null), Args.Dbl(a, "timeout", DefaultTimeout));
            return _client;
        }

        // ------------------------------------------------------------------
        // Du an
        // ------------------------------------------------------------------

        private static void DropProject()
        {
            if (_project != null)
            {
                Free(_project);
                _project = null;
            }
        }

        private static void LoadProject()
        {
            _project = _client.ProjectManager.GetActiveProject();
            if (_project != null)
                _project.ProjectClosed += delegate { _project = null; };
        }

        private static Project Proj(Dictionary<string, object> a)
        {
            EnsureClient(a);
            if (_project == null) LoadProject();
            if (_project == null)
                throw new Exception("Chua co du an nao dang mo trong Trimble Connect for Desktop. " +
                                    "Hay mo mot project roi thu lai.");
            return _project;
        }

        private static Dictionary<string, object> ProjectInfo(Project p)
        {
            return Map("name", p.Name, "identifier", p.Identifier, "location", p.Location);
        }

        // ------------------------------------------------------------------
        // Model
        // ------------------------------------------------------------------

        private static List<Model> FetchModels(Project p, string state)
        {
            IEnumerable<Model> src;
            switch ((state ?? "all").ToLowerInvariant())
            {
                case "loaded": src = p.ModelManager.GetLoadedModels(); break;
                case "unloaded": src = p.ModelManager.GetUnloadedModels(); break;
                case "all": src = p.ModelManager.GetAllModels(); break;
                default: throw new Exception("state phai la all | loaded | unloaded, nhan duoc: " + state);
            }
            return src == null ? new List<Model>() : src.ToList();
        }

        private static Dictionary<string, object> ModelInfo(Model m, bool loaded)
        {
            var d = Map("identifier", m.Identifier, "name", m.Name, "version", m.VersionIdentifier);
            d["loaded"] = loaded;
            return d;
        }

        private static object ListModels(Dictionary<string, object> a)
        {
            var p = Proj(a);
            string state = Args.Str(a, "state", "all").ToLowerInvariant();

            var all = FetchModels(p, "all");
            List<Model> loaded = null;
            try
            {
                loaded = state == "all" ? FetchModels(p, "loaded") : null;
                var loadedIds = new HashSet<string>(
                    (loaded ?? new List<Model>()).Select(m => m.Identifier));

                List<Model> shown;
                if (state == "all") shown = all;
                else
                {
                    var subset = FetchModels(p, state);
                    try
                    {
                        var ids = new HashSet<string>(subset.Select(m => m.Identifier));
                        shown = all.Where(m => ids.Contains(m.Identifier)).ToList();
                        if (state == "loaded") loadedIds = ids;
                    }
                    finally { FreeAll(subset); }
                }

                var rows = shown
                    .Select(m => ModelInfo(m, state == "unloaded" ? false : loadedIds.Contains(m.Identifier)))
                    .ToList();
                return Map("models", rows, "count", rows.Count, "state", state);
            }
            finally
            {
                if (loaded != null) FreeAll(loaded);
                FreeAll(all);
            }
        }

        private static object SetModelsLoaded(Dictionary<string, object> a, bool load)
        {
            var p = Proj(a);
            var ids = Args.RequiredList(a, "model_ids");
            bool excludeFromScope = Args.Bool(a, "exclude_from_scope", false);

            var all = FetchModels(p, "all");
            try
            {
                var chosen = all.Where(m => ids.Contains(m.Identifier)).ToList();
                var missing = ids.Where(id => !all.Any(m => m.Identifier == id)).ToList();
                if (chosen.Count == 0)
                    throw new Exception("Khong tim thay model nao khop. Id khong co: " +
                                        string.Join(", ", missing.ToArray()));

                bool ok = load
                    ? p.ModelManager.LoadModels(chosen)
                    : p.ModelManager.UnloadModels(chosen, excludeFromScope);

                return Map("success", ok,
                           "affected", chosen.Select(m => m.Identifier).ToList(),
                           "not_found", missing);
            }
            finally { FreeAll(all); }
        }

        private static Model RequireModel(Project p, string modelId)
        {
            var all = FetchModels(p, "all");
            Model found = null;
            foreach (var m in all)
                if (m.Identifier == modelId) { found = m; break; }

            foreach (var m in all)
                if (!ReferenceEquals(m, found)) Free(m);

            if (found == null)
                throw new Exception("Khong tim thay model voi identifier: " + modelId);
            return found;
        }

        private static object PlacementJson(ModelPlacement pl)
        {
            if (pl == null) return null;
            return Map("position_x", pl.PositionX, "position_y", pl.PositionY, "elevation", pl.Elevation,
                       "scale", pl.Scale, "rotation_x", pl.RotationX, "rotation_y", pl.RotationY,
                       "rotation_z", pl.RotationZ);
        }

        private static object GetModelPlacement(Dictionary<string, object> a)
        {
            var p = Proj(a);
            var m = RequireModel(p, Args.Required(a, "model_id"));
            try { return Map("model_id", m.Identifier, "placement", PlacementJson(m.GetPlacement())); }
            finally { Free(m); }
        }

        private static object SetModelPlacement(Dictionary<string, object> a)
        {
            var p = Proj(a);
            var m = RequireModel(p, Args.Required(a, "model_id"));
            try
            {
                var applied = new List<string>();

                double? x = Args.DblOpt(a, "position_x");
                double? y = Args.DblOpt(a, "position_y");
                double? z = Args.DblOpt(a, "elevation");
                if (x.HasValue || y.HasValue || z.HasValue)
                {
                    var cur = m.GetPlacement();
                    if (cur == null) throw new Exception("Khong doc duoc placement hien tai cua model.");
                    if (!m.SetPosition(x ?? cur.PositionX, y ?? cur.PositionY, z ?? cur.Elevation))
                        throw new Exception("SetPosition that bai.");
                    applied.Add("position");
                }

                double? scale = Args.DblOpt(a, "scale");
                if (scale.HasValue)
                {
                    if (!m.SetScale(scale.Value)) throw new Exception("SetScale that bai.");
                    applied.Add("scale");
                }

                double? angle = Args.DblOpt(a, "rotation_angle");
                if (angle.HasValue)
                {
                    var axis = Args.AsEnum(a, "rotation_axis", RotationAxis.Z);
                    if (!m.SetRotation(angle.Value, axis)) throw new Exception("SetRotation that bai.");
                    applied.Add("rotation");
                }

                if (applied.Count == 0)
                    throw new Exception("Khong co gia tri nao de dat. Truyen position_x/position_y/elevation, " +
                                        "scale hoac rotation_angle (+rotation_axis).");

                return Map("model_id", m.Identifier, "applied", applied,
                           "placement", PlacementJson(m.GetPlacement()));
            }
            finally { Free(m); }
        }

        private static object ResetModelPlacement(Dictionary<string, object> a)
        {
            var p = Proj(a);
            var m = RequireModel(p, Args.Required(a, "model_id"));
            try
            {
                bool ok = m.ResetPlacement();
                return Map("success", ok, "model_id", m.Identifier, "placement", PlacementJson(m.GetPlacement()));
            }
            finally { Free(m); }
        }

        private static object GetModelContentPath(Dictionary<string, object> a)
        {
            var p = Proj(a);
            var m = RequireModel(p, Args.Required(a, "model_id"));
            try { return Map("model_id", m.Identifier, "name", m.Name, "content_path", m.GetContentPath()); }
            finally { Free(m); }
        }

        // ------------------------------------------------------------------
        // Doi tuong
        // ------------------------------------------------------------------

        /// <summary>Lay ModelObjectManager theo pham vi du an hoac mot model.</summary>
        private static ModelObjectManager ScopedManager(Project p, Dictionary<string, object> a, out Model owner)
        {
            owner = null;
            string modelId = Args.Str(a, "model_id", null);
            if (modelId == null) return p.ModelObjectManager;
            owner = RequireModel(p, modelId);
            return owner.ModelObjectManager;
        }

        private static ObjectSelectionMode Mode(Dictionary<string, object> a)
        {
            return Args.AsEnum(a, "selection_mode", ObjectSelectionMode.Undefined);
        }

        private static List<ModelObject> Query(ModelObjectManager mgr, Filter filter, ObjectSelectionMode mode)
        {
            IEnumerable<ModelObject> res = filter == null
                ? mgr.GetModelObjects(mode)
                : mgr.GetModelObjects(filter, mode);
            return res == null ? new List<ModelObject>() : res.ToList();
        }

        private static List<ModelObject> ByIds(ModelObjectManager mgr, List<string> ids,
                                               bool onlyParts, ObjectSelectionMode mode)
        {
            var found = Query(mgr, new ModelObjectIdentifierFilter(ids, onlyParts), mode);
            if (found.Count == 0)
                throw new Exception("Khong tim thay doi tuong nao voi cac identifier da cho.");
            return found;
        }

        private static Filter BuildFilter(Dictionary<string, object> a)
        {
            string by = Args.Str(a, "by", "all").ToLowerInvariant();
            switch (by)
            {
                case "all":
                    return null;
                case "selected":
                    return new SelectionFilter(Args.Bool(a, "selected", true));
                case "type":
                    return new ModelObjectTypeFilter(Args.Required(a, "type_name"));
                case "visual_state":
                case "visualstate":
                    return new VisualStateFilter(Args.AsEnum(a, "visual_state", VisualState.Visible));
                case "attribute":
                    return new AttributeFilter(Args.Required(a, "attribute_name"),
                                               Args.Str(a, "attribute_value", null),
                                               Args.Str(a, "attribute_set", null));
                case "ids":
                    return new ModelObjectIdentifierFilter(Args.RequiredList(a, "ids"),
                                                           Args.Bool(a, "only_parts", false));
                default:
                    throw new Exception("by phai la all | selected | type | visual_state | attribute | ids, " +
                                        "nhan duoc: " + by);
            }
        }

        private static object ObjectsPayload(List<ModelObject> objects, int limit, bool withTypeName)
        {
            var rows = new List<object>();
            int take = limit <= 0 ? objects.Count : Math.Min(limit, objects.Count);
            for (int i = 0; i < take; i++)
            {
                var o = objects[i];
                var d = Map("identifier", o.Identifier, "model_identifier", o.ModelIdentifier);
                if (withTypeName)
                {
                    try { d["type_name"] = o.GetModelObjectTypeName(); }
                    catch (Exception ex) { d["type_name_error"] = Program.Flatten(ex); }
                }
                rows.Add(d);
            }
            return Map("objects", rows, "returned", rows.Count, "total", objects.Count,
                       "truncated", rows.Count < objects.Count);
        }

        private static object FindObjects(Dictionary<string, object> a)
        {
            var p = Proj(a);
            Model owner;
            var mgr = ScopedManager(p, a, out owner);
            List<ModelObject> objects = null;
            try
            {
                objects = Query(mgr, BuildFilter(a), Mode(a));
                var payload = (Dictionary<string, object>)ObjectsPayload(
                    objects, Args.Int(a, "limit", DefaultLimit), Args.Bool(a, "with_type_name", false));

                if (Args.Bool(a, "with_type_summary", false))
                {
                    try
                    {
                        var names = mgr.GetModelObjectTypeNames(objects);
                        payload["type_names"] = names == null ? new List<string>() : names.ToList();
                    }
                    catch (Exception ex) { payload["type_names_error"] = Program.Flatten(ex); }
                }
                return payload;
            }
            finally
            {
                if (objects != null) FreeAll(objects);
                if (owner != null) Free(owner);
            }
        }

        private static object GetSelection(Dictionary<string, object> a)
        {
            var p = Proj(a);
            Model owner;
            var mgr = ScopedManager(p, a, out owner);
            List<ModelObject> objects = null;
            try
            {
                objects = Query(mgr, new SelectionFilter(true), Mode(a));
                return ObjectsPayload(objects, Args.Int(a, "limit", DefaultLimit),
                                      Args.Bool(a, "with_type_name", false));
            }
            finally
            {
                if (objects != null) FreeAll(objects);
                if (owner != null) Free(owner);
            }
        }

        /// <summary>Nap doi tuong theo id roi chay mot thao tac hang loat len chung.</summary>
        private static object WithObjects(Dictionary<string, object> a,
                                          Func<ModelObjectManager, List<ModelObject>, object> action)
        {
            var p = Proj(a);
            Model owner;
            var mgr = ScopedManager(p, a, out owner);
            List<ModelObject> objects = null;
            try
            {
                objects = ByIds(mgr, Args.RequiredList(a, "ids"), Args.Bool(a, "only_parts", false), Mode(a));
                return action(mgr, objects);
            }
            finally
            {
                if (objects != null) FreeAll(objects);
                if (owner != null) Free(owner);
            }
        }

        private static object SelectObjects(Dictionary<string, object> a)
        {
            bool selected = Args.Bool(a, "selected", true);
            return WithObjects(a, (mgr, objs) => Map(
                "success", mgr.SetSelected(selected, objs),
                "count", objs.Count,
                "selected", selected));
        }

        private static object SetVisualState(Dictionary<string, object> a)
        {
            var state = Args.AsEnum(a, "visual_state", VisualState.Visible);
            return WithObjects(a, (mgr, objs) => Map(
                "success", mgr.SetVisualState(state, objs),
                "count", objs.Count,
                "visual_state", state.ToString()));
        }

        private static object ResetVisualState(Dictionary<string, object> a)
        {
            return WithObjects(a, (mgr, objs) => Map(
                "success", mgr.ResetVisualState(objs), "count", objs.Count));
        }

        private static object SetColor(Dictionary<string, object> a)
        {
            var color = Args.AsColor(a, "color");
            return WithObjects(a, (mgr, objs) => Map(
                "success", mgr.SetColor(color, objs),
                "count", objs.Count,
                "color", ColorTranslator.ToHtml(color)));
        }

        private static object ResetColor(Dictionary<string, object> a)
        {
            return WithObjects(a, (mgr, objs) => Map(
                "success", mgr.ResetColor(objs), "count", objs.Count));
        }

        /// <summary>An tat ca roi chi hien lai nhung doi tuong duoc chon.</summary>
        private static object IsolateObjects(Dictionary<string, object> a)
        {
            var p = Proj(a);
            Model owner;
            var mgr = ScopedManager(p, a, out owner);
            List<ModelObject> keep = null;
            List<ModelObject> all = null;
            try
            {
                var mode = Mode(a);

                // Chot danh sach giu lai truoc khi an, neu khong mot lenh sai
                // se an sach model ma khong hien lai duoc gi.
                var ids = Args.StrList(a, "ids");
                keep = ids.Count > 0
                    ? ByIds(mgr, ids, Args.Bool(a, "only_parts", false), mode)
                    : Query(mgr, new SelectionFilter(true), mode);

                if (keep.Count == 0)
                    throw new Exception("Khong co doi tuong nao de isolate (ids rong va cung khong co gi dang chon).");

                all = Query(mgr, null, mode);
                if (all.Count > 0) mgr.SetVisualState(VisualState.Hidden, all);
                bool ok = mgr.SetVisualState(VisualState.Visible, keep);

                return Map("success", ok, "visible", keep.Count, "hidden", Math.Max(0, all.Count - keep.Count));
            }
            finally
            {
                if (all != null) FreeAll(all);
                if (keep != null) FreeAll(keep);
                if (owner != null) Free(owner);
            }
        }

        /// <summary>Tra moi doi tuong ve trang thai hien thi va mau goc.</summary>
        private static object ResetAll(Dictionary<string, object> a)
        {
            var p = Proj(a);
            Model owner;
            var mgr = ScopedManager(p, a, out owner);
            List<ModelObject> all = null;
            try
            {
                all = Query(mgr, null, Mode(a));
                var result = Map("count", all.Count);
                if (all.Count > 0)
                {
                    if (Args.Bool(a, "visual_state", true))
                        result["visual_state_reset"] = mgr.ResetVisualState(all);
                    if (Args.Bool(a, "color", true))
                        result["color_reset"] = mgr.ResetColor(all);
                }
                return result;
            }
            finally
            {
                if (all != null) FreeAll(all);
                if (owner != null) Free(owner);
            }
        }

        private static object GetObjectAttributes(Dictionary<string, object> a)
        {
            int limit = Args.Int(a, "limit", 20);
            return WithObjects(a, (mgr, objs) =>
            {
                var rows = new List<object>();
                int take = limit <= 0 ? objs.Count : Math.Min(limit, objs.Count);
                for (int i = 0; i < take; i++)
                {
                    var o = objs[i];
                    var d = Map("identifier", o.Identifier, "model_identifier", o.ModelIdentifier);
                    try { d["type_name"] = o.GetModelObjectTypeName(); }
                    catch { }
                    try
                    {
                        var sets = o.GetAttributeSets();
                        d["attribute_sets"] = sets == null
                            ? new List<object>()
                            : sets.Select(s => AttributeSetJson(s)).ToList();
                    }
                    catch (Exception ex) { d["error"] = Program.Flatten(ex); }
                    rows.Add(d);
                }
                return Map("objects", rows, "returned", rows.Count, "total", objs.Count,
                           "truncated", rows.Count < objs.Count);
            });
        }

        private static object GetAttributeNames(Dictionary<string, object> a)
        {
            var p = Proj(a);
            Model owner;
            var mgr = ScopedManager(p, a, out owner);
            List<ModelObject> objects = null;
            try
            {
                var ids = Args.StrList(a, "ids");
                objects = ids.Count > 0
                    ? ByIds(mgr, ids, Args.Bool(a, "only_parts", false), Mode(a))
                    : Query(mgr, new SelectionFilter(true), Mode(a));

                if (objects.Count == 0)
                    throw new Exception("Khong co doi tuong nao (ids rong va cung khong co gi dang chon).");

                var attrMgr = owner == null ? p.AttributeManager : owner.AttributeManager;
                var src = attrMgr.GetAttributeNames(objects);
                var names = src == null ? new List<string>() : src.ToList();
                return Map("attribute_names", names, "count", names.Count, "objects", objects.Count);
            }
            finally
            {
                if (objects != null) FreeAll(objects);
                if (owner != null) Free(owner);
            }
        }

        private static object GetAttribute(Dictionary<string, object> a)
        {
            string attrName = Args.Required(a, "attribute_name");
            string setName = Args.Str(a, "attribute_set", null);
            int limit = Args.Int(a, "limit", 100);

            return WithObjects(a, (mgr, objs) =>
            {
                var rows = new List<object>();
                int take = limit <= 0 ? objs.Count : Math.Min(limit, objs.Count);
                for (int i = 0; i < take; i++)
                {
                    var o = objs[i];
                    var d = Map("identifier", o.Identifier, "model_identifier", o.ModelIdentifier);
                    try
                    {
                        var sets = o.GetAttribute(attrName, setName);
                        d["attribute_sets"] = sets == null
                            ? new List<object>()
                            : sets.Select(s => AttributeSetJson(s)).ToList();
                    }
                    catch (Exception ex) { d["error"] = Program.Flatten(ex); }
                    rows.Add(d);
                }
                return Map("attribute_name", attrName, "attribute_set", setName,
                           "objects", rows, "returned", rows.Count, "total", objs.Count);
            });
        }

        private static object GetRelatedObjects(Dictionary<string, object> a)
        {
            var relation = Args.AsEnum(a, "relation", HierarchyRelation.Child);
            var level = Args.AsEnum(a, "level", HierarchyLevel.Immediate);
            int limit = Args.Int(a, "limit", DefaultLimit);

            return WithObjects(a, (mgr, objs) =>
            {
                var rows = new List<object>();
                foreach (var o in objs)
                {
                    List<ModelObject> related = null;
                    try
                    {
                        var src = relation == HierarchyRelation.Child
                            ? o.GetChildren(level)
                            : o.GetParents(level);
                        related = src == null ? new List<ModelObject>() : src.ToList();
                        rows.Add(Map("identifier", o.Identifier,
                                     "related", ObjectsPayload(related, limit, false)));
                    }
                    catch (Exception ex)
                    {
                        rows.Add(Map("identifier", o.Identifier, "error", Program.Flatten(ex)));
                    }
                    finally { if (related != null) FreeAll(related); }
                }
                return Map("relation", relation.ToString(), "level", level.ToString(), "results", rows);
            });
        }

        // ------------------------------------------------------------------
        // View
        // ------------------------------------------------------------------

        private static List<View> FetchViews(Project p)
        {
            var src = p.ViewManager.GetViews();
            return src == null ? new List<View>() : src.ToList();
        }

        private static object ListViews(Dictionary<string, object> a)
        {
            var p = Proj(a);
            var views = FetchViews(p);
            var rows = views.Select(v => Map("identifier", v.Identifier, "name", v.Name)).ToList();
            return Map("views", rows, "count", rows.Count);
        }

        private static object ActivateView(Dictionary<string, object> a)
        {
            var p = Proj(a);
            string id = Args.Str(a, "identifier", null);
            string name = Args.Str(a, "name", null);
            if (id == null && name == null)
                throw new Exception("Can identifier hoac name cua view.");

            var views = FetchViews(p);
            View target = null;
            foreach (var v in views)
            {
                if (id != null && v.Identifier == id) { target = v; break; }
                if (id == null && string.Equals(v.Name, name, StringComparison.OrdinalIgnoreCase)) { target = v; break; }
            }
            if (target == null)
                throw new Exception("Khong tim thay view. Cac view dang co: " +
                                    string.Join(", ", views.Select(v => v.Name).ToArray()));

            return Map("success", p.ViewManager.ActivateView(target),
                       "identifier", target.Identifier, "name", target.Name);
        }

        private static object CreateView(Dictionary<string, object> a)
        {
            var p = Proj(a);
            var view = p.ViewManager.CreateView(Args.Required(a, "name"));
            if (view == null) throw new Exception("Tao view that bai.");
            return Map("identifier", view.Identifier, "name", view.Name);
        }

        // ------------------------------------------------------------------
        // Viewport
        // ------------------------------------------------------------------

        private static object Vec(Vector3 v)
        {
            if (v == null) return null;
            return Map("x", v.X, "y", v.Y, "z", v.Z);
        }

        private static Vector3 VecFrom(Dictionary<string, object> a, string key, Vector3 fallback)
        {
            object raw;
            if (a == null || !a.TryGetValue(key, out raw) || raw == null) return fallback;

            var arr = Args.AsList(raw);
            if (arr != null && arr.Count >= 3)
                return new Vector3(Convert.ToDouble(arr[0], CultureInfo.InvariantCulture),
                                   Convert.ToDouble(arr[1], CultureInfo.InvariantCulture),
                                   Convert.ToDouble(arr[2], CultureInfo.InvariantCulture));

            var obj = raw as Dictionary<string, object>;
            if (obj != null)
            {
                double x = Args.Dbl(obj, "x", fallback == null ? 0 : fallback.X);
                double y = Args.Dbl(obj, "y", fallback == null ? 0 : fallback.Y);
                double z = Args.Dbl(obj, "z", fallback == null ? 0 : fallback.Z);
                return new Vector3(x, y, z);
            }
            throw new Exception(key + " phai la [x,y,z] hoac {x,y,z}.");
        }

        private static object CameraJson(Camera c)
        {
            if (c == null) return null;
            return Map("location", Vec(c.Location), "direction", Vec(c.Direction), "up", Vec(c.Up),
                       "projection", c.ProjectionType.ToString(),
                       "view_angle", c.ViewAngle, "view_scale", c.ViewScale);
        }

        private static object GetCamera(Dictionary<string, object> a)
        {
            var p = Proj(a);
            return Map("camera", CameraJson(p.ViewportManager.GetCamera()));
        }

        private static object SetCamera(Dictionary<string, object> a)
        {
            var p = Proj(a);
            var vpm = p.ViewportManager;

            var cam = vpm.GetCamera() ?? new Camera();
            cam.Location = VecFrom(a, "location", cam.Location);
            cam.Direction = VecFrom(a, "direction", cam.Direction);
            cam.Up = VecFrom(a, "up", cam.Up);
            cam.ProjectionType = Args.AsEnum(a, "projection", cam.ProjectionType);

            double? angle = Args.DblOpt(a, "view_angle");
            if (angle.HasValue) cam.ViewAngle = angle.Value;
            double? scale = Args.DblOpt(a, "view_scale");
            if (scale.HasValue) cam.ViewScale = scale.Value;

            bool ok = vpm.SetCamera(cam, Args.Dbl(a, "duration", 0.0));
            return Map("success", ok, "camera", CameraJson(vpm.GetCamera()));
        }

        private static object ZoomToObjects(Dictionary<string, object> a)
        {
            var p = Proj(a);
            var vpm = p.ViewportManager;
            Model owner;
            var mgr = ScopedManager(p, a, out owner);
            List<ModelObject> objects = null;
            try
            {
                var ids = Args.StrList(a, "ids");
                objects = ids.Count > 0
                    ? ByIds(mgr, ids, Args.Bool(a, "only_parts", false), Mode(a))
                    : Query(mgr, new SelectionFilter(true), Mode(a));

                if (objects.Count == 0)
                    throw new Exception("Khong co doi tuong nao de zoom (danh sach ids rong va cung khong co gi dang chon).");

                return Map("success", vpm.SetCamera(objects), "count", objects.Count,
                           "camera", CameraJson(vpm.GetCamera()));
            }
            finally
            {
                if (objects != null) FreeAll(objects);
                if (owner != null) Free(owner);
            }
        }

        private static object SetSelectionMode(Dictionary<string, object> a)
        {
            var client = EnsureClient(a);
            var mode = Args.AsEnum(a, "mode", ObjectSelectionMode.Undefined);
            if (mode == ObjectSelectionMode.Undefined)
                throw new Exception("mode phai la HighestLevelAssembliesAndSystems hoac IndividualObjects.");
            bool ok = client.SettingsManager.SetObjectSelectionMode(mode);
            return Map("success", ok, "selection_mode", client.SettingsManager.GetObjectSelectionMode().ToString());
        }

        // ------------------------------------------------------------------
        // Thuoc tinh -> JSON
        // ------------------------------------------------------------------

        private static object AttributeSetJson(TcAttributeSet set)
        {
            if (set == null) return null;
            var attrs = new List<object>();
            AddAttributes(attrs, set.StringAttributes);
            AddAttributes(attrs, set.IntAttributes);
            AddAttributes(attrs, set.DoubleAttributes);
            AddAttributes(attrs, set.BooleanAttributes);
            AddAttributes(attrs, set.DateTimeAttributes);
            AddAttributes(attrs, set.LengthAttributes);
            AddAttributes(attrs, set.AreaAttributes);
            AddAttributes(attrs, set.VolumeAttributes);
            AddAttributes(attrs, set.MassAttributes);
            return Map("name", set.Name, "attributes", attrs, "count", attrs.Count);
        }

        // Moi lop thuoc tinh co mot property Value voi kieu rieng; lay bang reflection
        // de khong phai viet 9 nhanh giong nhau.
        private static void AddAttributes(List<object> sink, IEnumerable source)
        {
            if (source == null) return;
            foreach (var item in source)
            {
                var at = item as TcAttribute;
                if (at == null) continue;

                object value = null;
                var prop = item.GetType().GetProperty("Value", BindingFlags.Public | BindingFlags.Instance);
                if (prop != null)
                {
                    try { value = prop.GetValue(item, null); }
                    catch { }
                }
                if (value is DateTime)
                    value = ((DateTime)value).ToString("o", CultureInfo.InvariantCulture);

                string kind = item.GetType().Name;
                if (kind.EndsWith("Attribute")) kind = kind.Substring(0, kind.Length - "Attribute".Length);

                sink.Add(Map("name", at.Name, "value", value, "formatted", at.FormattedValue, "kind", kind));
            }
        }

        // ------------------------------------------------------------------
        // Tien ich
        // ------------------------------------------------------------------

        private static Dictionary<string, object> Map(params object[] pairs)
        {
            var d = new Dictionary<string, object>();
            for (int i = 0; i + 1 < pairs.Length; i += 2)
                d[Convert.ToString(pairs[i], CultureInfo.InvariantCulture)] = pairs[i + 1];
            return d;
        }

        private static void Free(object o)
        {
            var d = o as IDisposable;
            if (d == null) return;
            try { d.Dispose(); }
            catch { }
        }

        private static void FreeAll(IEnumerable items)
        {
            if (items == null) return;
            foreach (var item in items) Free(item);
        }
    }
}
