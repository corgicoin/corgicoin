#include "sendcoinsdialog.h"
#include "ui_sendcoinsdialog.h"
#include "walletmodel.h"
#include "bitcoinunits.h"
#include "addressbookpage.h"
#include "optionsmodel.h"
#include "sendcoinsentry.h"
#include "guiutil.h"
#include "askpassphrasedialog.h"
#include "coincontroldialog.h"
#include "qvalidatedlineedit.h"
#include "base58.h"

#include <QMessageBox>
#include <QLocale>
#include <QTextDocument>
#include <QScrollBar>
#include <QCheckBox>
#include <QGroupBox>
#include <QGridLayout>
#include <QLabel>
#include <QPushButton>

SendCoinsDialog::SendCoinsDialog(QWidget *parent) :
    QDialog(parent),
    ui(new Ui::SendCoinsDialog),
    model(0)
{
    ui->setupUi(this);

#ifdef Q_OS_MACOS // Icons on push buttons are very uncommon on Mac
    ui->addButton->setIcon(QIcon());
    ui->clearButton->setIcon(QIcon());
    ui->sendButton->setIcon(QIcon());
#endif

    setupCoinControl();
    addEntry();

    connect(ui->addButton, &QPushButton::clicked, this, &SendCoinsDialog::addEntry);
    connect(ui->clearButton, &QPushButton::clicked, this, &SendCoinsDialog::clear);

    fNewRecipientAllowed = true;
}

void SendCoinsDialog::setModel(WalletModel *model)
{
    this->model = model;

    for(int i = 0; i < ui->entries->count(); ++i)
    {
        SendCoinsEntry *entry = qobject_cast<SendCoinsEntry*>(ui->entries->itemAt(i)->widget());
        if(entry)
        {
            entry->setModel(model);
        }
    }
    if(model && model->getOptionsModel())
    {
        setBalance(model->getBalance(), model->getUnconfirmedBalance(), model->getImmatureBalance());
        connect(model, &WalletModel::balanceChanged, this, &SendCoinsDialog::setBalance);
        connect(model->getOptionsModel(), &OptionsModel::displayUnitChanged, this, &SendCoinsDialog::updateDisplayUnit);
        // A selected coin may have been spent elsewhere; refresh the summary.
        connect(model, &WalletModel::balanceChanged, this, &SendCoinsDialog::updateCoinControlLabel);
    }
    updateCoinControlLabel();
}

SendCoinsDialog::~SendCoinsDialog()
{
    delete ui;
}

void SendCoinsDialog::on_sendButton_clicked()
{
    QList<SendCoinsRecipient> recipients;
    bool valid = true;

    if(!model)
        return;

    for(int i = 0; i < ui->entries->count(); ++i)
    {
        SendCoinsEntry *entry = qobject_cast<SendCoinsEntry*>(ui->entries->itemAt(i)->widget());
        if(entry)
        {
            if(entry->validate())
            {
                recipients.append(entry->getValue());
            }
            else
            {
                valid = false;
            }
        }
    }

    if(!valid || recipients.isEmpty())
    {
        return;
    }

    if(customChangeCheck->isChecked() && !coinControl.HasCustomChange())
    {
        customChangeEdit->setValid(false);
        QMessageBox::warning(this, tr("Send Coins"),
            tr("Enter a valid change address, or untick \"Custom change address\"."),
            QMessageBox::Ok, QMessageBox::Ok);
        return;
    }

    // Format confirmation message
    QStringList formatted;
    for (const SendCoinsRecipient &rcp : recipients)
    {
        formatted.append(tr("<b>%1</b> to %2 (%3)").arg(BitcoinUnits::formatWithUnit(BitcoinUnits::BTC, rcp.amount), rcp.label.toHtmlEscaped(), rcp.address));
    }

    fNewRecipientAllowed = false;

    QString question = tr("Are you sure you want to send %1?").arg(formatted.join(tr(" and ")));
    if(coinControl.HasSelected())
        question += "<br><br>" + coinControlLabel->text();
    if(coinControl.HasCustomChange())
        question += "<br>" + tr("Change goes to %1").arg(customChangeEdit->text().trimmed());
    QMessageBox::StandardButton retval = QMessageBox::question(this, tr("Confirm send coins"),
                          question,
          QMessageBox::Yes|QMessageBox::Cancel,
          QMessageBox::Cancel);

    if(retval != QMessageBox::Yes)
    {
        fNewRecipientAllowed = true;
        return;
    }

    WalletModel::UnlockContext ctx(model->requestUnlock());
    if(!ctx.isValid())
    {
        // Unlock wallet was cancelled
        fNewRecipientAllowed = true;
        return;
    }

    WalletModel::SendCoinsReturn sendstatus = model->sendCoins(recipients, &coinControl);
    switch(sendstatus.status)
    {
    case WalletModel::StatusCode::InvalidAddress:
        QMessageBox::warning(this, tr("Send Coins"),
            tr("The recepient address is not valid, please recheck."),
            QMessageBox::Ok, QMessageBox::Ok);
        break;
    case WalletModel::StatusCode::InvalidAmount:
        QMessageBox::warning(this, tr("Send Coins"),
            tr("The amount to pay must be larger than 0."),
            QMessageBox::Ok, QMessageBox::Ok);
        break;
    case WalletModel::StatusCode::AmountExceedsBalance:
        QMessageBox::warning(this, tr("Send Coins"),
            tr("The amount exceeds your balance."),
            QMessageBox::Ok, QMessageBox::Ok);
        break;
    case WalletModel::StatusCode::AmountWithFeeExceedsBalance:
        QMessageBox::warning(this, tr("Send Coins"),
            tr("The total exceeds your balance when the %1 transaction fee is included.").
            arg(BitcoinUnits::formatWithUnit(BitcoinUnits::BTC, sendstatus.fee)),
            QMessageBox::Ok, QMessageBox::Ok);
        break;
    case WalletModel::StatusCode::DuplicateAddress:
        QMessageBox::warning(this, tr("Send Coins"),
            tr("Duplicate address found, can only send to each address once per send operation."),
            QMessageBox::Ok, QMessageBox::Ok);
        break;
    case WalletModel::StatusCode::TransactionCreationFailed:
        QMessageBox::warning(this, tr("Send Coins"),
            tr("Error: Transaction creation failed."),
            QMessageBox::Ok, QMessageBox::Ok);
        break;
    case WalletModel::StatusCode::TransactionCommitFailed:
        QMessageBox::warning(this, tr("Send Coins"),
            tr("Error: The transaction was rejected. This might happen if some of the coins in your wallet were already spent, such as if you used a copy of wallet.dat and coins were spent in the copy but not marked as spent here."),
            QMessageBox::Ok, QMessageBox::Ok);
        break;
    case WalletModel::StatusCode::Aborted: // User aborted, nothing to do
        break;
    case WalletModel::StatusCode::OK:
        accept();
        break;
    }
    fNewRecipientAllowed = true;
}

void SendCoinsDialog::clear()
{
    coinControl.SetNull();
    customChangeCheck->setChecked(false);
    customChangeEdit->clear();
    updateCoinControlLabel();

    // Remove entries until only one left
    while(ui->entries->count())
    {
        delete ui->entries->takeAt(0)->widget();
    }
    addEntry();

    updateRemoveEnabled();

    ui->sendButton->setDefault(true);
}

void SendCoinsDialog::reject()
{
    clear();
}

void SendCoinsDialog::accept()
{
    clear();
}

SendCoinsEntry *SendCoinsDialog::addEntry()
{
    SendCoinsEntry *entry = new SendCoinsEntry(this);
    entry->setModel(model);
    ui->entries->addWidget(entry);
    connect(entry, &SendCoinsEntry::removeEntry, this, &SendCoinsDialog::removeEntry);

    updateRemoveEnabled();

    // Focus the field, so that entry can start immediately
    entry->clear();
    entry->setFocus();
    ui->scrollAreaWidgetContents->resize(ui->scrollAreaWidgetContents->sizeHint());
    QCoreApplication::instance()->processEvents();
    QScrollBar* bar = ui->scrollArea->verticalScrollBar();
    if(bar)
        bar->setSliderPosition(bar->maximum());
    return entry;
}

void SendCoinsDialog::updateRemoveEnabled()
{
    // Remove buttons are enabled as soon as there is more than one send-entry
    bool enabled = (ui->entries->count() > 1);
    for(int i = 0; i < ui->entries->count(); ++i)
    {
        SendCoinsEntry *entry = qobject_cast<SendCoinsEntry*>(ui->entries->itemAt(i)->widget());
        if(entry)
        {
            entry->setRemoveEnabled(enabled);
        }
    }
    setupTabChain(0);
}

void SendCoinsDialog::removeEntry(SendCoinsEntry* entry)
{
    delete entry;
    updateRemoveEnabled();
}

QWidget *SendCoinsDialog::setupTabChain(QWidget *prev)
{
    for(int i = 0; i < ui->entries->count(); ++i)
    {
        SendCoinsEntry *entry = qobject_cast<SendCoinsEntry*>(ui->entries->itemAt(i)->widget());
        if(entry)
        {
            prev = entry->setupTabChain(prev);
        }
    }
    QWidget::setTabOrder(prev, ui->addButton);
    QWidget::setTabOrder(ui->addButton, ui->sendButton);
    return ui->sendButton;
}

void SendCoinsDialog::pasteEntry(const SendCoinsRecipient &rv)
{
    if(!fNewRecipientAllowed)
        return;

    SendCoinsEntry *entry = 0;
    // Replace the first entry if it is still unused
    if(ui->entries->count() == 1)
    {
        SendCoinsEntry *first = qobject_cast<SendCoinsEntry*>(ui->entries->itemAt(0)->widget());
        if(first->isClear())
        {
            entry = first;
        }
    }
    if(!entry)
    {
        entry = addEntry();
    }

    entry->setValue(rv);
}

bool SendCoinsDialog::handleURI(const QString &uri)
{
    SendCoinsRecipient rv;
    // URI has to be valid
    if (GUIUtil::parseBitcoinURI(uri, &rv))
    {
        pasteEntry(rv);
        return true;
    }

    return false;
}

void SendCoinsDialog::setBalance(qint64 balance, qint64 unconfirmedBalance, qint64 immatureBalance)
{
    Q_UNUSED(unconfirmedBalance);
    Q_UNUSED(immatureBalance);
    if(!model || !model->getOptionsModel())
        return;

    int unit = model->getOptionsModel()->getDisplayUnit();
    ui->labelBalance->setText(BitcoinUnits::formatWithUnit(unit, balance));
}

void SendCoinsDialog::updateDisplayUnit()
{
    if(model && model->getOptionsModel())
    {
        // Update labelBalance with the current balance and the current unit
        ui->labelBalance->setText(BitcoinUnits::formatWithUnit(model->getOptionsModel()->getDisplayUnit(), model->getBalance()));
    }
}

void SendCoinsDialog::setupCoinControl()
{
    QGroupBox *box = new QGroupBox(tr("Coin Control"), this);
    QGridLayout *grid = new QGridLayout(box);

    coinControlButton = new QPushButton(tr("Inputs..."), box);
    coinControlButton->setToolTip(tr("Choose exactly which coins this payment spends, or lock coins"));
    coinControlLabel = new QLabel(box);

    customChangeCheck = new QCheckBox(tr("Custom change address"), box);
    customChangeCheck->setToolTip(tr("Send any change to this address instead of a new one from the wallet"));
    customChangeEdit = new QValidatedLineEdit(box);
    customChangeEdit->setPlaceholderText(tr("Change address"));
    customChangeEdit->setEnabled(false);
    customChangeStatus = new QLabel(box);

    grid->addWidget(coinControlButton, 0, 0);
    grid->addWidget(coinControlLabel, 0, 1, 1, 2);
    grid->addWidget(customChangeCheck, 1, 0);
    grid->addWidget(customChangeEdit, 1, 1);
    grid->addWidget(customChangeStatus, 1, 2);
    grid->setColumnStretch(1, 1);

    ui->verticalLayout->insertWidget(0, box);

    connect(coinControlButton, &QPushButton::clicked, this, &SendCoinsDialog::coinControlButtonClicked);
    connect(customChangeCheck, &QCheckBox::toggled, this, &SendCoinsDialog::customChangeToggled);
    connect(customChangeEdit, &QValidatedLineEdit::textChanged, this, &SendCoinsDialog::customChangeEdited);
}

void SendCoinsDialog::coinControlButtonClicked()
{
    if(!model)
        return;
    CoinControlDialog dlg(&coinControl, model, this);
    dlg.exec();
    updateCoinControlLabel();
}

void SendCoinsDialog::updateCoinControlLabel()
{
    if(!model || !model->getOptionsModel())
    {
        coinControlLabel->setText(QString());
        return;
    }
    if(!coinControl.HasSelected())
    {
        coinControlLabel->setText(tr("Inputs: chosen automatically"));
        return;
    }
    std::vector<COutPoint> vSelected;
    coinControl.ListSelected(vSelected);
    coinControlLabel->setText(tr("Inputs: %n coin(s) picked, totalling %1", "", (int)vSelected.size())
        .arg(BitcoinUnits::formatWithUnit(model->getOptionsModel()->getDisplayUnit(),
                                          model->getSelectedBalance(coinControl))));
}

void SendCoinsDialog::customChangeToggled(bool checked)
{
    customChangeEdit->setEnabled(checked);
    if(checked)
        customChangeEdit->setFocus();
    customChangeEdited();
}

void SendCoinsDialog::customChangeEdited()
{
    coinControl.destChange = CNoDestination();
    customChangeStatus->clear();
    customChangeEdit->setValid(true);
    if(!customChangeCheck->isChecked() || !model)
        return;

    QString text = customChangeEdit->text().trimmed();
    if(text.isEmpty())
        return;

    CBitcoinAddress addr(text.toStdString());
    if(!addr.IsValid())
    {
        customChangeEdit->setValid(false);
        customChangeStatus->setText(tr("Invalid address"));
        return;
    }
    coinControl.destChange = addr.Get();
    if(!model->isMine(text))
        customChangeStatus->setText(tr("Warning: not an address in this wallet"));
}
