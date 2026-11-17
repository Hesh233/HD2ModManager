using System.Diagnostics;
using System.Windows.Controls;
using System.Windows.Navigation;

namespace HD2ModManager.Views
{
    public partial class HomePageView : UserControl
    {
        public static string SkeletonRepairTitle => Services.SkeletonTestBuild.HomeTitle;
        public static string SkeletonRepairNotes => Services.SkeletonTestBuild.ReleaseNotes;

        public HomePageView()
        {
            InitializeComponent();
        }

        private void OnHelpLinkRequestNavigate(object sender, RequestNavigateEventArgs e)
        {
            Process.Start(new ProcessStartInfo(e.Uri.AbsoluteUri) { UseShellExecute = true });
            e.Handled = true;
        }
    }
}
