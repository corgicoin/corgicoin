#include "qvaluecombobox.h"

QValueComboBox::QValueComboBox(QWidget *parent) :
        QComboBox(parent), role(Qt::UserRole)
{
    connect(this, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &QValueComboBox::handleSelectionChanged);
}

QVariant QValueComboBox::value() const
{
    return itemData(currentIndex(), role);
}

void QValueComboBox::setValue(const QVariant &value)
{
    setCurrentIndex(findData(value, role));
}

void QValueComboBox::setRole(int role)
{
    this->role = role;
}

void QValueComboBox::handleSelectionChanged(int idx)
{
    emit valueChanged();
}
