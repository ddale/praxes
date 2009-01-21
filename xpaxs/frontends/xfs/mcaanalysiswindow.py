"""
"""

#---------------------------------------------------------------------------
# Stdlib imports
#---------------------------------------------------------------------------

from __future__ import absolute_import

import copy
import gc
import logging

#---------------------------------------------------------------------------
# Extlib imports
#---------------------------------------------------------------------------

from PyQt4 import QtCore, QtGui
from PyMca.FitParam import FitParamDialog
import numpy

#---------------------------------------------------------------------------
# xpaxs imports
#---------------------------------------------------------------------------

from ..base.mainwindow import MainWindowBase
from .ui.ui_mcaanalysiswindow import Ui_McaAnalysisWindow
from .elementsview import ElementsView
from xpaxs.io.phynx import H5Error

#---------------------------------------------------------------------------
# Normal code begins
#---------------------------------------------------------------------------

logger = logging.getLogger(__file__)


class McaAnalysisWindow(Ui_McaAnalysisWindow, MainWindowBase):

    """
    """

    # TODO: this should eventually take an MCA entry
    def __init__(self, scanData, parent=None):
        super(McaAnalysisWindow, self).__init__(parent)
        self.scanData = scanData['measurement']
        self.setupUi(self)

        title = '%s: %s'%(
            scanData.file_name,
            scanData.name
        )
        self.setWindowTitle(title)

#        self.scanData = scanData
#        self.connect(
#            self.scanData,
#            QtCore.SIGNAL("dataInitialized"),
#            self.updateNormalizationChannels
#        )

        self.elementsView = ElementsView(self.scanData, self)

        self.xrfBandComboBox.addItems(self.availableElements)
        self.updateNormalizationChannels()

        self._setupMcaDockWindows()
        self._setupPPJobStats()

        plotOptions = self.elementsView.plotOptions
        self.gridLayout.addWidget(plotOptions, 4, 0, 1, 2)

        self.connect(
            self.elementsView,
            QtCore.SIGNAL("pickEvent"),
            self.processAverageSpectrum
        )
        # TODO: remove the window from the list of open windows when we close
#        self.connect(scanView, QtCore.SIGNAL("scanClosed"), self.scanClosed)

        self.verticalLayout.addWidget(self.elementsView)

        self.fitParamDlg = FitParamDialog(parent=self)
        pymcaConfig = self.scanData.mcas[0].pymca_config

        if pymcaConfig:
            self.fitParamDlg.setParameters(pymcaConfig)
            self.spectrumAnalysis.configure(pymcaConfig)
        else:
            self.configurePymca()

        self.progressBar = QtGui.QProgressBar(self)
        self.progressBar.setMaximumHeight(17)
        self.progressBar.hide()
        self.progressBar.addAction(self.actionAbort)
        self.progressBar.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.analysisThread = None

        self.elementsView.updateFigure()

        self._restoreSettings()

    @property
    def availableElements(self):
        try:
            return sorted(self.scanData['element_maps'].fits.keys())
        except (H5Error, AttributeError):
            return []

    @property
    def mapType(self):
        return str(self.mapTypeComboBox.currentText()).lower().replace(' ', '_')

    @property
    def normalization(self):
        return str(self.normalizationComboBox.currentText())

    @property
    def xrfBand(self):
        return str(self.xrfBandComboBox.currentText())

    @property
    def pymcaConfig(self):
        return self.fitParamDlg.getParameters()

    def _setupMcaDockWindows(self):
        from xpaxs.frontends.xfs.mcaspectrum import McaSpectrum
        from PyMca.ConcentrationsWidget import Concentrations

        self.concentrationsAnalysisDock = \
            self._createDockWindow('ConcentrationAnalysisDock')
        self.concentrationsAnalysis = Concentrations()
        self._setupDockWindow(
            self.concentrationsAnalysisDock,
            QtCore.Qt.BottomDockWidgetArea,
            self.concentrationsAnalysis,
            'Concentrations Analysis'
        )

        self.spectrumAnalysisDock = \
            self._createDockWindow('SpectrumAnalysisDock')
        self.spectrumAnalysis = McaSpectrum(self.concentrationsAnalysis)
        self._setupDockWindow(
            self.spectrumAnalysisDock,
            QtCore.Qt.BottomDockWidgetArea,
            self.spectrumAnalysis,
            'Spectrum Analysis'
        )

    def _setupPPJobStats(self):
        from xpaxs.frontends.base.ppjobstats import PPJobStats

        self.ppJobStats = PPJobStats()
        self.ppJobStatsDock = self._createDockWindow('PPJobStatsDock')
        self._setupDockWindow(self.ppJobStatsDock,
                               QtCore.Qt.RightDockWidgetArea,
                               self.ppJobStats, 'Analysis Server Stats')

    @QtCore.pyqtSignature("bool")
    def on_actionAbort_triggered(self):
        try:
            self.analysisThread.stop()
        except AttributeError:
            pass

    @QtCore.pyqtSignature("bool")
    def on_actionAnalyzeSpectra_triggered(self):
        self.processData()

    @QtCore.pyqtSignature("bool")
    def on_actionConfigurePymca_triggered(self):
        self.configurePymca()

    @QtCore.pyqtSignature("bool")
    def on_actionCalibration_triggered(self):
        self.processAverageSpectrum()

    @QtCore.pyqtSignature("QString")
    def on_mapTypeComboBox_currentIndexChanged(self):
        self.elementsView.updateFigure(self.getElementMap())

    @QtCore.pyqtSignature("QString")
    def on_normalizationComboBox_currentIndexChanged(self):
        self.scanData.mcas[0].normalization_channel = \
            self.normalization

    @QtCore.pyqtSignature("QString")
    def on_xrfBandComboBox_currentIndexChanged(self):
        self.elementsView.updateFigure(self.getElementMap())

    def closeEvent(self, event):
        if self.analysisThread:
            warning = '''Data analysis is not yet complete.
            Are you sure you want to close?'''
            res = QtGui.QMessageBox.question(self, 'closing...', warning,
                                             QtGui.QMessageBox.Yes,
                                             QtGui.QMessageBox.No)
            if res == QtGui.QMessageBox.Yes:
                if self.analysisThread:
                    self.analysisThread.stop()
                    self.analysisThread.wait()
                    QtGui.qApp.processEvents()
            else:
                return event.ignore()

#        self.scanData.flush()

        # TODO: improve this to close scans in the file interface
        self.emit(QtCore.SIGNAL("scanClosed"), self)

        if MainWindowBase.closeEvent(self, event):
            return event.accept()

    def configurePymca(self):
        if self.fitParamDlg.exec_():
            # TODO: is this needed?
            QtGui.qApp.processEvents()

            self.statusBar.showMessage('Reconfiguring PyMca ...')
            configDict = self.fitParamDlg.getParameters()
            self.spectrumAnalysis.configure(configDict)
            self.scanData.mcas[0].pymca_config = configDict
            self.statusBar.clearMessage()

    def elementMapUpdated(self):
        self.elementsView.updateFigure(self.getElementMap())

    def getElementMap(self, mapType=None, element=None):
        if element is None: element = self.xrfBand
        if mapType is None: mapType = self.mapType

        if mapType and element:
            try:
                entry = '%s_%s'%(element, mapType)
                return self.scanData['element_maps'][entry].map

            except H5Error:
                return numpy.zeros(self.scanData.acquisition_shape)

        else:
            return numpy.zeros(self.scanData.acquisition_shape, dtype='f')

    def initializeElementMaps(self, elements):
        if 'element_maps' in self.scanData:
            del self.scanData['element_maps']

        elementMaps = self.scanData.create_group(
            'element_maps', type='ElementMaps'
        )

        for mapType, cls in [
            ('fit', 'Fit'),
            ('fit_error', 'FitError'),
            ('mass_fraction', 'MassFraction')
        ]:
            for element in elements:
                entry = '%s_%s'%(element, mapType)
                elementMaps.create_dataset(
                    entry,
                    type=cls,
                    data=numpy.zeros(self.scanData.npoints, 'f')
                )

#    def updateElementMap(self, mapType, element, index, val):
#        try:
#            entry = '%s_%s'%(element, mapType)
#            self.scanData['element_maps'][entry][tuple(index)] = val
#        except ValueError:
#            print index, node

    def processAverageSpectrum(self, indices=None):
        self.statusBar.showMessage('Validating data points ...')
        valid = self.scanData['scalar_data'].valid_indices
        if indices is None:
            indices = valid
        else:
            indices = valid[indices]
        if len(indices):
            self.statusBar.showMessage('Averaging spectra ...')
            counts = self.scanData.mcas[0].get_averaged_counts(
                indices
            )
            channels = self.scanData.mcas[0].channels

            self.spectrumAnalysis.setData(x=channels, y=counts)

            self.statusBar.showMessage('Performing Fit ...')
            fitresult = self.spectrumAnalysis.fit()

            self.fitParamDlg.setFitResult(fitresult['result'])

            self.statusBar.clearMessage()

        self.setMenuToolsActionsEnabled(True)

    def processComplete(self):
        self.progressBar.hide()
        self.progressBar.reset()
        self.statusBar.removeWidget(self.progressBar)
        self.statusBar.clearMessage()

        self.analysisThread = None

        self.setMenuToolsActionsEnabled(True)

    def processData(self):
        from xpaxs.frontends.xfs.pptaskmanager import XfsPPTaskManager

        self.setMenuToolsActionsEnabled(False)

        self._resetPeaks()

        thread = XfsPPTaskManager(parent=self)
#        config = copy.deepcopy(self.pymcaConfig)
#        thread.setData(self.scanData, config)
        thread.setData(self.scanData, self.pymcaConfig)

        self.connect(
            thread,
            QtCore.SIGNAL('dataProcessed'),
            self.elementMapUpdated
        )
        self.connect(
            thread,
            QtCore.SIGNAL('ppJobStats'),
            self.ppJobStats.updateTable
        )
        self.connect(
            thread,
            QtCore.SIGNAL("finished()"),
            self.elementMapUpdated
        )
        self.connect(
            thread,
            QtCore.SIGNAL("finished()"),
            self.processComplete
        )
        self.connect(
            thread,
            QtCore.SIGNAL('percentComplete'),
            self.progressBar.setValue
        )
#        self.connect(
#            self.actionAbort,
#            QtCore.SIGNAL('triggered(bool)'),
#            thread.stop
#        )

        self.statusBar.showMessage('Analyzing spectra ...')
        self.statusBar.addPermanentWidget(self.progressBar)
        self.progressBar.show()

        self.analysisThread = thread

        thread.start(QtCore.QThread.NormalPriority)

    def _resetPeaks(self):
        peaks = []

        for el, edges in self.pymcaConfig['peaks'].iteritems():
            for edge in edges:
                name = '_'.join([el, edge])
                peaks.append(name)

        peaks.sort()
        self.initializeElementMaps(peaks)

        self.xrfBandComboBox.clear()
        self.xrfBandComboBox.addItems(peaks)

    def setMenuToolsActionsEnabled(self, enabled=True):
        self.actionAnalyzeSpectra.setEnabled(enabled)
        self.actionConfigurePymca.setEnabled(enabled)
        self.actionCalibration.setEnabled(enabled)

    def updateNormalizationChannels(self):
        norm = self.scanData.mcas[0].normalization_channel
        self.normalizationComboBox.clear()
        self.normalizationComboBox.addItems(
            ['', 'None'] + sorted(self.scanData.mcas[0].signals.keys())
        )
        i = self.normalizationComboBox.findText(norm)
        self.normalizationComboBox.setCurrentIndex(i)


if __name__ == "__main__":
    import sys
    app = QtGui.QApplication(sys.argv)
    app.setOrganizationName('XPaXS')
    form = MainWindowBase()
    form.show()
    sys.exit(app.exec_())
