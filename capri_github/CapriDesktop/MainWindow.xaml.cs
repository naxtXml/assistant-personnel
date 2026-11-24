using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace CapriDesktop
{
    public partial class MainWindow : Window
    {
        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

        private static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        private const uint SWP_NOMOVE = 0x0002;
        private const uint SWP_NOSIZE = 0x0001;
        private const uint SWP_NOACTIVATE = 0x0010;

        private readonly GifPlayer _gifPlayer = new GifPlayer();
        private DispatcherTimer? _typewriterTimer;
        private string _fullTextToType = "";
        private int _typewriterIndex = 0;
        private double _lastBottom = 0;
        private TcpListener? _listener;
        private bool _isRunning = true;
        private string _currentState = "idle";

        public MainWindow()
        {
            InitializeComponent();
            Loaded += MainWindow_Loaded;
            SizeChanged += MainWindow_SizeChanged;
            Deactivated += (s, e) => EnsureTopmost();
        }

        private void MainWindow_Loaded(object sender, RoutedEventArgs e)
        {
            _lastBottom = Top + ActualHeight;
            SetAvatarState("idle");
            EnsureTopmost();
            StartLocalServer();
        }

        public void EnsureTopmost()
        {
            try
            {
                Topmost = true;
                var hwnd = new WindowInteropHelper(this).Handle;
                if (hwnd != IntPtr.Zero)
                {
                    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
                }
            }
            catch { }
        }

        private void MainWindow_SizeChanged(object sender, SizeChangedEventArgs e)
        {
            if (e.HeightChanged && _lastBottom > 0)
            {
                Top = _lastBottom - ActualHeight;
            }
            EnsureTopmost();
        }

        // ==========================================
        // GESTION DU DIALOGUE & DURÉE DU GIF
        // ==========================================
        public void Speak(string text, string targetState = "speaking", int durationSeconds = 0)
        {
            Dispatcher.Invoke(async () =>
            {
                _fullTextToType = text ?? "";
                _typewriterIndex = 0;
                DialogueText.Text = "";

                DateTime startTime = DateTime.Now;

                // 1. Démarre le GIF immédiatement
                SetAvatarState(targetState);
                EnsureTopmost();

                _typewriterTimer?.Stop();

                // 2. Petit temps d'animation avant le début des lettres
                await Task.Delay(250);

                if (_fullTextToType != text) return;

                // 3. Écriture machine à écrire
                _typewriterTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(28) };
                _typewriterTimer.Tick += async (s, ev) =>
                {
                    if (_typewriterIndex < _fullTextToType.Length)
                    {
                        DialogueText.Text += _fullTextToType[_typewriterIndex];
                        _typewriterIndex++;
                    }
                    else
                    {
                        _typewriterTimer.Stop();

                        if (targetState == "eteint") return;

                        // Si c'est l'ennui ou qu'une durée est demandée (ex: 10 secondes)
                        int totalDurationMs = durationSeconds > 0 ? durationSeconds * 1000 : (targetState == "ennuie" ? 10000 : 0);
                        int elapsedMs = (int)(DateTime.Now - startTime).TotalMilliseconds;
                        int remainingMs = totalDurationMs - elapsedMs;

                        if (remainingMs > 0)
                        {
                            await Task.Delay(remainingMs);
                        }

                        // Retour à l'état de repos si aucune nouvelle action n'est intervenue
                        if (_fullTextToType == text && _currentState != "eteint")
                        {
                            SetAvatarState("idle");
                        }
                    }
                };
                _typewriterTimer.Start();
            });
        }

        public void SetAvatarState(string state)
        {
            _currentState = (state ?? "idle").ToLower().Trim();

            string targetFile;
            string badgeText;

            switch (_currentState)
            {
                case "speaking":
                case "parle":
                    targetFile = "capri_speaking.gif";
                    badgeText = "CAPRI // SPEAKING";
                    break;

                case "ennuie":
                case "bored":
                    targetFile = "capri_ennuie.gif";
                    badgeText = "CAPRI // BORED";
                    break;

                case "eteint":
                case "off":
                case "sleep":
                    targetFile = "capri_eteint.gif";
                    badgeText = "CAPRI // OFFLINE";
                    break;

                case "idle":
                default:
                    targetFile = "capri_base.png";
                    badgeText = "CAPRI // IDLE";
                    break;
            }

            AvatarStatus.Text = badgeText;
            string? path = FindAssetPath(targetFile);

            if (path == null || !File.Exists(path))
            {
                path = FindAssetPath("capri_base.png");
            }

            if (path == null || !File.Exists(path)) return;

            if (path.EndsWith(".gif", StringComparison.OrdinalIgnoreCase))
            {
                _gifPlayer.Start(path, (frame, w, h) =>
                {
                    AvatarImage.Source = frame;
                    AdjustFrameSize(w, h);
                });
            }
            else
            {
                _gifPlayer.Stop();
                BitmapImage bmp = new BitmapImage();
                bmp.BeginInit();
                bmp.CacheOption = BitmapCacheOption.OnLoad;
                bmp.UriSource = new Uri(path, UriKind.Absolute);
                bmp.EndInit();

                AvatarImage.Source = bmp;
                AdjustFrameSize(bmp.PixelWidth, bmp.PixelHeight);
            }
        }

        private void AdjustFrameSize(double pixelWidth, double pixelHeight)
        {
            if (pixelWidth <= 0 || pixelHeight <= 0) return;

            double maxW = 380;
            double maxH = 340;

            double ratio = Math.Min(maxW / pixelWidth, maxH / pixelHeight);
            double newW = Math.Round(pixelWidth * ratio);
            double newH = Math.Round(pixelHeight * ratio);

            if (AvatarBorder.Width != newW || AvatarBorder.Height != newH)
            {
                AvatarBorder.Width = newW;
                AvatarBorder.Height = newH;
            }
        }

        private string? FindAssetPath(string fileName)
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string[] testPaths = {
                Path.Combine(baseDir, fileName),
                Path.Combine(baseDir, "..", "..", "..", fileName),
                Path.Combine(Environment.CurrentDirectory, fileName)
            };

            foreach (var p in testPaths)
            {
                if (File.Exists(p)) return Path.GetFullPath(p);
            }
            return null;
        }

        private void StartLocalServer()
        {
            new Thread(() =>
            {
                try
                {
                    _listener = new TcpListener(IPAddress.Loopback, 45789);
                    _listener.Start();

                    while (_isRunning)
                    {
                        TcpClient client = _listener.AcceptTcpClient();
                        using (var reader = new StreamReader(client.GetStream(), Encoding.UTF8))
                        {
                            string? line = reader.ReadLine();
                            if (!string.IsNullOrWhiteSpace(line))
                            {
                                try
                                {
                                    using (var doc = JsonDocument.Parse(line))
                                    {
                                        string text = doc.RootElement.TryGetProperty("text", out var tProp) ? (tProp.GetString() ?? "") : "";
                                        string state = doc.RootElement.TryGetProperty("state", out var sProp) ? (sProp.GetString() ?? "speaking") : "speaking";
                                        int duration = doc.RootElement.TryGetProperty("duration", out var dProp) ? dProp.GetInt32() : 0;

                                        Speak(text, state, duration);
                                    }
                                }
                                catch
                                {
                                    Speak(line, "speaking");
                                }
                            }
                        }
                    }
                }
                catch { }
            })
            { IsBackground = true }.Start();
        }

        private void Window_MouseDown(object sender, MouseButtonEventArgs e)
        {
            if (e.ChangedButton == MouseButton.Left)
            {
                _lastBottom = Top + ActualHeight;
                DragMove();
                _lastBottom = Top + ActualHeight;
            }
        }

        private void Close_Click(object sender, RoutedEventArgs e)
        {
            _isRunning = false;
            _gifPlayer.Stop();
            try { _listener?.Stop(); } catch { }
            Close();
        }
    }

    public class GifPlayer
    {
        private DispatcherTimer? _timer;
        private GifBitmapDecoder? _decoder;
        private int _frameIndex;
        private Action<BitmapFrame, double, double>? _onFrame;

        public void Start(string gifPath, Action<BitmapFrame, double, double> onFrame)
        {
            Stop();
            _onFrame = onFrame;

            try
            {
                _decoder = new GifBitmapDecoder(new Uri(gifPath, UriKind.Absolute), BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
                if (_decoder.Frames.Count == 0) return;

                double w = _decoder.Frames[0].PixelWidth;
                double h = _decoder.Frames[0].PixelHeight;

                _frameIndex = 0;
                _onFrame?.Invoke(_decoder.Frames[0], w, h);

                if (_decoder.Frames.Count > 1)
                {
                    _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(70) };
                    _timer.Tick += (s, e) =>
                    {
                        if (_decoder != null && _decoder.Frames.Count > 0)
                        {
                            _frameIndex = (_frameIndex + 1) % _decoder.Frames.Count;
                            _onFrame?.Invoke(_decoder.Frames[_frameIndex], w, h);
                        }
                    };
                    _timer.Start();
                }
            }
            catch { }
        }

        public void Stop()
        {
            _timer?.Stop();
            _timer = null;
            _decoder = null;
            _onFrame = null;
        }
    }
}