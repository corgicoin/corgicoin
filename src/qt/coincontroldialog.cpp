#include "coincontroldialog.h"

#include "addresstablemodel.h"
#include "bitcoinunits.h"
#include "guiutil.h"
#include "optionsmodel.h"
#include "walletmodel.h"

#include "base58.h"
#include "coincontrol.h"
#include "wallet.h"

#include <QApplication>
#include <QClipboard>
#include <QDialogButtonBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QMenu>
#include <QPushButton>
#include <QTreeWidget>
#include <QVBoxLayout>

namespace {

// Per-item data, kept on the checkbox column.
constexpr int TxHashRole = Qt::UserRole;
constexpr int VoutRole = Qt::UserRole + 1;
constexpr int LockedRole = Qt::UserRole + 2;
// Numeric sort key for the amount, date and confirmations columns.
constexpr int SortRole = Qt::UserRole + 3;

class CoinItem : public QTreeWidgetItem
{
public:
    using QTreeWidgetItem::QTreeWidgetItem;

    bool operator<(const QTreeWidgetItem &other) const override
    {
        int column = treeWidget() ? treeWidget()->sortColumn() : 0;
        QVariant a = data(column, SortRole), b = other.data(column, SortRole);
        if (a.isValid() && b.isValid())
            return a.toLongLong() < b.toLongLong();
        return QTreeWidgetItem::operator<(other);
    }
};

COutPoint outpointOf(const QTreeWidgetItem *item)
{
    uint256 hash;
    hash.SetHex(item->data(CoinControlDialog::COLUMN_CHECKBOX, TxHashRole).toString().toStdString());
    return COutPoint(hash, item->data(CoinControlDialog::COLUMN_CHECKBOX, VoutRole).toUInt());
}

} // namespace

CoinControlDialog::CoinControlDialog(CCoinControl *coinControl, WalletModel *model, QWidget *parent) :
    QDialog(parent), coinControl(coinControl), model(model), contextItem(nullptr)
{
    setWindowTitle(tr("Coin Control"));
    resize(860, 460);

    QLabel *help = new QLabel(tr("Tick the coins this payment should spend. All ticked coins are used; "
                                 "if none are ticked, coins are chosen automatically. "
                                 "Right-click a coin to lock it so it is never spent automatically."), this);
    help->setWordWrap(true);

    tree = new QTreeWidget(this);
    tree->setColumnCount(6);
    tree->setHeaderLabels({QString(), tr("Amount"), tr("Label"), tr("Address"), tr("Date"), tr("Confirmations")});
    tree->setRootIsDecorated(false);
    tree->setAlternatingRowColors(true);
    tree->setSortingEnabled(true);
    tree->setContextMenuPolicy(Qt::CustomContextMenu);
    tree->header()->setSectionResizeMode(COLUMN_ADDRESS, QHeaderView::Stretch);
    tree->header()->setStretchLastSection(false);

    selectAllButton = new QPushButton(tr("(un)select all"), this);
    labelSummary = new QLabel(this);
    labelSummary->setTextInteractionFlags(Qt::TextSelectableByMouse);

    QDialogButtonBox *buttons = new QDialogButtonBox(QDialogButtonBox::Ok, this);

    QHBoxLayout *bottom = new QHBoxLayout();
    bottom->addWidget(selectAllButton);
    bottom->addWidget(labelSummary, 1);
    bottom->addWidget(buttons);

    QVBoxLayout *layout = new QVBoxLayout(this);
    layout->addWidget(help);
    layout->addWidget(tree, 1);
    layout->addLayout(bottom);

    contextMenu = new QMenu(this);
    contextMenu->addAction(tr("Copy amount"), this, &CoinControlDialog::copyAmount);
    contextMenu->addAction(tr("Copy address"), this, &CoinControlDialog::copyAddress);
    contextMenu->addAction(tr("Copy transaction ID"), this, &CoinControlDialog::copyTransactionHash);
    contextMenu->addSeparator();
    lockAction = contextMenu->addAction(QIcon(":/icons/lock_closed"), tr("Lock coin"), this, &CoinControlDialog::lockCoin);
    unlockAction = contextMenu->addAction(QIcon(":/icons/lock_open"), tr("Unlock coin"), this, &CoinControlDialog::unlockCoin);

    connect(tree, &QTreeWidget::itemChanged, this, &CoinControlDialog::itemChanged);
    connect(tree, &QTreeWidget::customContextMenuRequested, this, &CoinControlDialog::showMenu);
    connect(selectAllButton, &QPushButton::clicked, this, &CoinControlDialog::selectAllClicked);
    connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);

    populate();
}

void CoinControlDialog::populate()
{
    if (!model)
        return;

    int unit = model->getOptionsModel()->getDisplayUnit();

    std::vector<COutput> vCoins, vLocked;
    model->listCoins(vCoins);
    model->listLockedCoins(vLocked);

    // Drop selections that are no longer spendable (spent, or locked since).
    std::vector<COutPoint> vSelected;
    coinControl->ListSelected(vSelected);
    for (const COutPoint &outpoint : vSelected)
    {
        bool fFound = false;
        for (const COutput &out : vCoins)
            if (out.tx->GetHash() == outpoint.hash && (unsigned int)out.i == outpoint.n)
                fFound = true;
        if (!fFound)
            coinControl->UnSelect(outpoint);
    }

    tree->blockSignals(true);
    tree->setSortingEnabled(false);
    tree->clear();
    contextItem = nullptr;

    auto addRow = [&](const COutput &out, bool fLocked) {
        const CTxOut &txout = out.tx->vout[out.i];
        CoinItem *item = new CoinItem(tree);
        uint256 hash = out.tx->GetHash();

        item->setData(COLUMN_CHECKBOX, TxHashRole, QString::fromStdString(hash.GetHex()));
        item->setData(COLUMN_CHECKBOX, VoutRole, out.i);
        item->setData(COLUMN_CHECKBOX, LockedRole, fLocked);

        CTxDestination dest;
        QString address;
        if (ExtractDestination(txout.scriptPubKey, dest))
            address = QString::fromStdString(CBitcoinAddress(dest).ToString());
        QString label = model->getAddressTableModel()->labelForAddress(address);
        if (label.isEmpty() && !address.isEmpty())
            label = tr("(change)");

        item->setText(COLUMN_AMOUNT, BitcoinUnits::format(unit, txout.nValue));
        item->setData(COLUMN_AMOUNT, SortRole, (qlonglong)txout.nValue);
        item->setTextAlignment(COLUMN_AMOUNT, Qt::AlignRight | Qt::AlignVCenter);
        item->setText(COLUMN_LABEL, label);
        item->setText(COLUMN_ADDRESS, address);
        item->setText(COLUMN_DATE, GUIUtil::dateTimeStr(out.tx->GetTxTime()));
        item->setData(COLUMN_DATE, SortRole, (qlonglong)out.tx->GetTxTime());
        item->setText(COLUMN_CONFIRMATIONS, QString::number(out.nDepth));
        item->setData(COLUMN_CONFIRMATIONS, SortRole, (qlonglong)out.nDepth);
        item->setTextAlignment(COLUMN_CONFIRMATIONS, Qt::AlignRight | Qt::AlignVCenter);
        item->setToolTip(COLUMN_ADDRESS, tr("Transaction %1, output %2").arg(QString::fromStdString(hash.GetHex())).arg(out.i));

        if (fLocked)
        {
            // Locked coins can't be picked until they're unlocked.
            item->setFlags(item->flags() & ~Qt::ItemIsUserCheckable);
            item->setIcon(COLUMN_CHECKBOX, QIcon(":/icons/lock_closed"));
            item->setToolTip(COLUMN_CHECKBOX, tr("Locked: never spent automatically. Right-click to unlock."));
            for (int c = COLUMN_AMOUNT; c <= COLUMN_CONFIRMATIONS; c++)
                item->setForeground(c, tree->palette().brush(QPalette::Disabled, QPalette::Text));
        }
        else
        {
            item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
            item->setCheckState(COLUMN_CHECKBOX, coinControl->IsSelected(hash, out.i) ? Qt::Checked : Qt::Unchecked);
        }
    };

    for (const COutput &out : vCoins)
        addRow(out, false);
    for (const COutput &out : vLocked)
        addRow(out, true);

    tree->setSortingEnabled(true);
    tree->sortByColumn(COLUMN_AMOUNT, Qt::DescendingOrder);
    for (int c = COLUMN_CHECKBOX; c <= COLUMN_CONFIRMATIONS; c++)
        if (c != COLUMN_ADDRESS)
            tree->resizeColumnToContents(c);
    tree->blockSignals(false);

    updateSummary();
}

void CoinControlDialog::updateSummary()
{
    int unit = model->getOptionsModel()->getDisplayUnit();
    int nSelected = 0;
    qint64 nAmount = 0;
    for (int i = 0; i < tree->topLevelItemCount(); i++)
    {
        QTreeWidgetItem *item = tree->topLevelItem(i);
        if (item->checkState(COLUMN_CHECKBOX) == Qt::Checked)
        {
            nSelected++;
            nAmount += item->data(COLUMN_AMOUNT, SortRole).toLongLong();
        }
    }
    if (nSelected == 0)
        labelSummary->setText(tr("No coins ticked: coins will be chosen automatically."));
    else
        labelSummary->setText(tr("%n coin(s) ticked, totalling %1", "", nSelected)
                              .arg(BitcoinUnits::formatWithUnit(unit, nAmount)));
}

void CoinControlDialog::itemChanged(QTreeWidgetItem *item, int column)
{
    if (column != COLUMN_CHECKBOX || item->data(COLUMN_CHECKBOX, LockedRole).toBool())
        return;
    if (item->checkState(COLUMN_CHECKBOX) == Qt::Checked)
        coinControl->Select(outpointOf(item));
    else
        coinControl->UnSelect(outpointOf(item));
    updateSummary();
}

void CoinControlDialog::selectAllClicked()
{
    // Tick everything unless everything is already ticked, then clear.
    bool fAllChecked = true;
    for (int i = 0; i < tree->topLevelItemCount(); i++)
    {
        QTreeWidgetItem *item = tree->topLevelItem(i);
        if (!item->data(COLUMN_CHECKBOX, LockedRole).toBool() && item->checkState(COLUMN_CHECKBOX) != Qt::Checked)
            fAllChecked = false;
    }
    Qt::CheckState state = fAllChecked ? Qt::Unchecked : Qt::Checked;
    for (int i = 0; i < tree->topLevelItemCount(); i++)
    {
        QTreeWidgetItem *item = tree->topLevelItem(i);
        if (!item->data(COLUMN_CHECKBOX, LockedRole).toBool())
            item->setCheckState(COLUMN_CHECKBOX, state); // itemChanged updates coinControl
    }
}

void CoinControlDialog::showMenu(const QPoint &point)
{
    contextItem = tree->itemAt(point);
    if (!contextItem)
        return;
    bool fLocked = contextItem->data(COLUMN_CHECKBOX, LockedRole).toBool();
    lockAction->setEnabled(!fLocked);
    unlockAction->setEnabled(fLocked);
    contextMenu->exec(QCursor::pos());
}

void CoinControlDialog::copyAmount()
{
    if (contextItem)
        QApplication::clipboard()->setText(contextItem->text(COLUMN_AMOUNT));
}

void CoinControlDialog::copyAddress()
{
    if (contextItem)
        QApplication::clipboard()->setText(contextItem->text(COLUMN_ADDRESS));
}

void CoinControlDialog::copyTransactionHash()
{
    if (contextItem)
        QApplication::clipboard()->setText(contextItem->data(COLUMN_CHECKBOX, TxHashRole).toString());
}

void CoinControlDialog::lockCoin()
{
    if (!contextItem)
        return;
    COutPoint outpoint = outpointOf(contextItem);
    coinControl->UnSelect(outpoint);
    model->lockCoin(outpoint);
    populate();
}

void CoinControlDialog::unlockCoin()
{
    if (!contextItem)
        return;
    model->unlockCoin(outpointOf(contextItem));
    populate();
}
