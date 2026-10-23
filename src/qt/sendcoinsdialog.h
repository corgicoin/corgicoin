#ifndef SENDCOINSDIALOG_H
#define SENDCOINSDIALOG_H

#include <QDialog>

#include "coincontrol.h"

namespace Ui {
    class SendCoinsDialog;
}
class WalletModel;
class SendCoinsEntry;
class SendCoinsRecipient;

class QValidatedLineEdit;

QT_BEGIN_NAMESPACE
class QCheckBox;
class QLabel;
class QPushButton;
class QUrl;
QT_END_NAMESPACE

/** Dialog for sending corgicoins */
class SendCoinsDialog : public QDialog
{
    Q_OBJECT

public:
    explicit SendCoinsDialog(QWidget *parent = 0);
    ~SendCoinsDialog();

    void setModel(WalletModel *model);

    /** Set up the tab chain manually, as Qt messes up the tab chain by default in some cases (issue http://bugreports.qt.nokia.com/browse/QTBUG-10907).
     */
    QWidget *setupTabChain(QWidget *prev);

    void pasteEntry(const SendCoinsRecipient &rv);
    bool handleURI(const QString &uri);

public slots:
    void clear();
    void reject();
    void accept();
    SendCoinsEntry *addEntry();
    void updateRemoveEnabled();
    void setBalance(qint64 balance, qint64 unconfirmedBalance, qint64 immatureBalance);

private:
    Ui::SendCoinsDialog *ui;
    WalletModel *model;
    bool fNewRecipientAllowed;

    // Coin control: hand-picked inputs and an optional custom change address
    CCoinControl coinControl;
    QPushButton *coinControlButton;
    QLabel *coinControlLabel;
    QCheckBox *customChangeCheck;
    QValidatedLineEdit *customChangeEdit;
    QLabel *customChangeStatus;
    void setupCoinControl();

private slots:
    void on_sendButton_clicked();
    void removeEntry(SendCoinsEntry* entry);
    void updateDisplayUnit();
    void coinControlButtonClicked();
    void updateCoinControlLabel();
    void customChangeToggled(bool checked);
    void customChangeEdited();
};

#endif // SENDCOINSDIALOG_H
